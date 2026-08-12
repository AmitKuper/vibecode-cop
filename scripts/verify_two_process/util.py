"""Repo paths and small process/hash helpers for the acceptance run."""

from __future__ import annotations

import hashlib
import os
import socket
import subprocess
import time
from pathlib import Path

# Same values as the original scripts/verify_local_two_process.py computed from
# its own location (scripts/..): the cop repo root and its workspace parent.
ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parent
COP_REPO = WORKSPACE / "vibecode-cop"
THIEF_REPO = WORKSPACE / "vibecode-thief"


def _python(repo: Path) -> Path:
    candidate = repo / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not candidate.is_file():
        raise RuntimeError(f"repository environment Python not found: {candidate}")
    return candidate


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_listener(port: int, process: subprocess.Popen, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"thief server exited before listening (exit {process.returncode})")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"thief server did not listen on port {port} within {timeout_s}s")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contains_private_nonce_key(value) -> bool:
    if isinstance(value, dict):
        return any(
            key in {"nonce", "nonces"} or _contains_private_nonce_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_private_nonce_key(item) for item in value)
    return False
