"""Orchestrator-side Watchdog wiring (Appendix E rule 7).

The match orchestrator launches an INDEPENDENT watchdog process and beats a
heartbeat from a background asyncio task every ``HEARTBEAT_INTERVAL_S``. A normal
``await`` on a slow peer keeps beating (the loop is not blocked, only suspended),
so the watchdog fires ONLY on a true wedge — a deadlock or a runaway synchronous
loop that stops the event loop. On a stale heartbeat the watchdog writes
``technical_loss`` evidence and SIGTERMs the orchestrator (controlled recovery).

This is orchestrator plumbing only: it never runs on the gameplay path and holds
no game state, so it cannot affect move selection. It complements the
per-worker crash/hang recovery already in ``WorkerProc`` (which handles a wedged
ROLE process); the watchdog covers the coordinating process itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import os

from ref3_match.runtime_cfg import REPO_ROOT

HEARTBEAT_INTERVAL_S = 5.0


class OrchestratorWatchdog:
    """Launch + heartbeat + teardown for the independent watchdog process."""

    def __init__(self, game_uid: str) -> None:
        out_dir = REPO_ROOT / "reports" / "ref3_matches"
        out_dir.mkdir(parents=True, exist_ok=True)
        tag = "".join(c if c.isalnum() or c in "-_" else "_" for c in (game_uid or "match"))
        self._hb = str(out_dir / f"heartbeat_{tag}.json")
        self._evidence = str(out_dir / f"watchdog_evidence_{tag}.json")
        self.game_uid = game_uid or "match"
        self._proc = None
        self._task: asyncio.Task | None = None
        self._step = 0

    async def start(self) -> None:
        """Spawn the watchdog process and begin heartbeating."""
        from cop_worker.reliability.watchdog import launch_watchdog_subprocess

        with contextlib.suppress(Exception):
            self._proc = launch_watchdog_subprocess(self._hb, self._evidence)
        self._task = asyncio.get_event_loop().create_task(self._beat_loop())

    async def _beat_loop(self) -> None:
        from cop_worker.reliability.watchdog import write_heartbeat

        while True:
            self._step += 1
            with contextlib.suppress(Exception):
                write_heartbeat(
                    self._hb,
                    pid=os.getpid(),
                    game_uid=self.game_uid,
                    session_id=str(os.getpid()),
                    step=self._step,
                    state_path=self._hb,
                )
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)

    async def stop(self) -> None:
        """Stop heartbeating and terminate the watchdog BEFORE teardown noise.

        Called first in the orchestrator's finally block so the watchdog can
        never SIGTERM us during a legitimate (possibly slow) shutdown.
        """
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        if self._proc is not None:
            with contextlib.suppress(Exception):
                self._proc.terminate()
