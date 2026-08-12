"""Port checks, subprocess stop, and inbox polling helpers."""

from __future__ import annotations

import asyncio
import socket
import subprocess
import time


def _check_port(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex((host, port)) == 0


async def _wait_port_async(host: str, port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _check_port(host, port):
            return
        await asyncio.sleep(0.15)
    raise TimeoutError(f"server did not listen on {host}:{port}")


def _stop(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(3)


async def _poll_deque(deque, *, timeout: float = 20.0, label: str) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if deque:
            return deque.popleft()
        await asyncio.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for {label} ({timeout}s)")


async def _poll_inbox_step(inbox, step: int, *, timeout: float = 20.0) -> None:
    """Wait until inbox has processed step."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if inbox.next_step > step:
            return
        await asyncio.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for inbox step {step}")
