"""Independent Watchdog process — NOT on the monitored event loop."""

import contextlib
import hashlib
import json
import os
import signal
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from league_manager.reliability.durable_io import atomic_write_json

HEARTBEAT_INTERVAL_S = 5.0  # main process must update this often
THRESHOLD_MULTIPLIER = 3.0  # declare dead after 3x interval without heartbeat


@dataclass
class HeartbeatRecord:
    pid: int
    game_uid: str
    session_id: str
    last_heartbeat_monotonic: float
    last_heartbeat_utc: str
    current_step: int
    state_path: str
    technical_loss_path: str = ""


def write_heartbeat(
    heartbeat_path: str,
    pid: int,
    game_uid: str,
    session_id: str,
    step: int,
    state_path: str,
    technical_loss_path: str = "",
) -> None:
    """Called by the main process to emit a heartbeat."""
    rec = HeartbeatRecord(
        pid=pid,
        game_uid=game_uid,
        session_id=session_id,
        last_heartbeat_monotonic=time.monotonic(),
        last_heartbeat_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        current_step=step,
        state_path=state_path,
        technical_loss_path=technical_loss_path,
    )
    atomic_write_json(heartbeat_path, asdict(rec))


def _read_heartbeat(path: str) -> HeartbeatRecord | None:
    try:
        with open(path) as f:
            d = json.load(f)
        return HeartbeatRecord(**d)
    except Exception:
        return None


def _write_failure_evidence(evidence_path: str, rec: HeartbeatRecord, reason: str) -> None:
    state_file = Path(rec.state_path)
    state_sha256 = ""
    if state_file.is_file():
        state_sha256 = hashlib.sha256(state_file.read_bytes()).hexdigest()
    evidence = {
        "reason": reason,
        "pid": rec.pid,
        "game_uid": rec.game_uid,
        "last_heartbeat_utc": rec.last_heartbeat_utc,
        "detected_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "watchdog_action": "SIGTERM",
        "recovery_state_path": rec.state_path,
        "recovery_state_sha256": state_sha256,
    }
    atomic_write_json(evidence_path, evidence)
    technical_loss_path = rec.technical_loss_path or str(
        Path(evidence_path).with_name("technical_loss_watchdog.json")
    )
    atomic_write_json(
        technical_loss_path,
        {
            **evidence,
            "protocol_state": "technical_loss",
            "subsystem": "watchdog",
        },
    )


def run_watchdog(heartbeat_path: str, evidence_path: str, threshold_s: float | None = None) -> None:
    """Main watchdog loop — runs in a separate process."""
    if threshold_s is None:
        threshold_s = HEARTBEAT_INTERVAL_S * THRESHOLD_MULTIPLIER

    while True:
        time.sleep(HEARTBEAT_INTERVAL_S)
        rec = _read_heartbeat(heartbeat_path)
        if rec is None:
            continue
        elapsed = time.monotonic() - rec.last_heartbeat_monotonic
        if elapsed > threshold_s:
            _write_failure_evidence(
                evidence_path,
                rec,
                f"Heartbeat stale for {elapsed:.1f}s > threshold {threshold_s:.1f}s",
            )
            with contextlib.suppress(ProcessLookupError):
                os.kill(rec.pid, signal.SIGTERM)
            # Watchdog stays alive to detect restart
            time.sleep(threshold_s)


def launch_watchdog_subprocess(
    heartbeat_path: str,
    evidence_path: str,
    threshold_s: float | None = None,
):
    """Launch watchdog as a separate OS process. Returns subprocess.Popen."""
    import subprocess

    script = f"""
import sys
sys.path.insert(0, ".")
from league_manager.reliability.watchdog import run_watchdog
run_watchdog({heartbeat_path!r}, {evidence_path!r}, threshold_s={threshold_s!r})
"""
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.Popen([sys.executable, "-c", script], creationflags=creationflags)
