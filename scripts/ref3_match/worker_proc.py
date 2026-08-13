"""Orchestrator-side handle for one role-worker process (spawn/request/restart).

JSON-lines over the child's stdio; the child's stderr (its human log, including
[wire<-] lines) is pumped into our stdout with a role prefix so the match log
stays one readable stream. The orchestrator holds NO game state for the role —
that is the whole point of the split (Appendix E rules 1-2).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from pathlib import Path

from ref3_match.runtime_cfg import REPO_ROOT

_LAUNCHER = REPO_ROOT / "scripts" / "ref3_role_worker.py"
_LINE_LIMIT = 16 * 1024 * 1024  # settled rows carry full logs; default 64KB would truncate


class WorkerProcError(RuntimeError):
    """The worker died or broke protocol; the caller decides how to file the window."""


class WorkerProc:
    """One spawned role worker: ready-gated, one in-flight request at a time."""

    def __init__(self, role: str, init: dict, launcher: Path | None = None) -> None:
        self.role = role
        self.init = dict(init, role=role)
        self.launcher = str(launcher or _LAUNCHER)
        self.proc: asyncio.subprocess.Process | None = None
        self._pump_task: asyncio.Task | None = None

    async def start(self, ready_timeout_s: float = 120.0) -> None:
        """Spawn the process, send init, pump stderr, await the ready frame."""
        self.proc = await asyncio.create_subprocess_exec(
            sys.executable,
            self.launcher,
            cwd=str(REPO_ROOT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=_LINE_LIMIT,
        )
        self._pump_task = asyncio.create_task(self._pump_stderr())
        self._send(self.init)
        frame = await self._recv(timeout_s=ready_timeout_s)
        if frame.get("type") != "ready":
            raise WorkerProcError(f"{self.role} worker sent {frame!r} instead of ready")
        print(f"[match] {self.role} worker ready (pid={self.proc.pid})")

    def _send(self, obj: dict) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise WorkerProcError(f"{self.role} worker not running")
        self.proc.stdin.write(json.dumps(obj, separators=(",", ":")).encode() + b"\n")

    async def _recv(self, *, timeout_s: float) -> dict:
        assert self.proc is not None and self.proc.stdout is not None
        try:
            line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=timeout_s)
        except TimeoutError as exc:
            raise WorkerProcError(f"{self.role} worker timed out after {timeout_s:.0f}s") from exc
        if not line:
            raise WorkerProcError(f"{self.role} worker exited (eof on stdout)")
        try:
            return json.loads(line)
        except ValueError as exc:
            raise WorkerProcError(f"{self.role} worker broke protocol: {line[:120]!r}") from exc

    async def request(self, cmd: dict, *, timeout_s: float) -> dict:
        """Send one command and await its single reply frame."""
        self._send(cmd)
        return await self._recv(timeout_s=timeout_s)

    async def _pump_stderr(self) -> None:
        assert self.proc is not None and self.proc.stderr is not None
        with contextlib.suppress(Exception):
            while True:
                line = await self.proc.stderr.readline()
                if not line:
                    return
                text = line.decode(errors="replace").rstrip()
                if text:
                    print(f"[{self.role[0]}w] {text}")

    async def stop(self, grace_s: float = 8.0) -> None:
        """Polite shutdown, then kill; always reaps the process and the pump."""
        if self.proc is None:
            return
        with contextlib.suppress(Exception):
            self._send({"type": "shutdown"})
        try:
            await asyncio.wait_for(self.proc.wait(), timeout=grace_s)
        except (TimeoutError, ProcessLookupError):
            with contextlib.suppress(ProcessLookupError):
                self.proc.kill()
            with contextlib.suppress(Exception):
                await self.proc.wait()
        if self._pump_task is not None:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(self._pump_task, timeout=3.0)
        self.proc = None

    async def restart(self) -> None:
        """Kill and respawn after a hang — the watchdog move (Appendix E rule 7)."""
        print(f"[match] RESTARTING wedged {self.role} worker")
        await self.stop(grace_s=0.5)
        await self.start()


def absorb_strays(pending: dict, frame: dict) -> None:
    """Bank a frame's misrouted greetings by sub-game for later re-injection."""
    for g in frame.get("stray_greetings") or []:
        n = g.get("sub_game_number")
        if isinstance(n, int):
            pending.setdefault(n, []).append(g)


async def drain_other(worker: WorkerProc, pending: dict) -> None:
    """Pull misrouted greetings out of the idle worker before dispatching a window."""
    with contextlib.suppress(Exception):
        absorb_strays(pending, await worker.request({"type": "drain"}, timeout_s=10.0))
