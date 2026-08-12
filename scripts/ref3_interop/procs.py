"""Process/port helpers for the interop verifier: spawn hygiene, waits, git."""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path


def _hidden_process_kwargs() -> dict:
    if os.name != "nt":
        return {}
    return {"creationflags": subprocess.CREATE_NO_WINDOW}


def _wait_port(host: str, port: int, process: subprocess.Popen, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited before listening (exit {process.returncode})")
        with socket.socket() as sock:
            sock.settimeout(0.2)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.1)
    raise TimeoutError(f"server did not listen on {host}:{port}")


def _stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _git(kit: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(kit), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
