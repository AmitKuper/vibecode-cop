"""Independent Watchdog process — NOT on the monitored event loop."""

import contextlib
import json
import os
import signal
import sys
import time
from dataclasses import asdict, dataclass

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


def write_heartbeat(
    heartbeat_path: str,
    pid: int,
    game_uid: str,
    session_id: str,
    step: int,
    state_path: str,
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
    )
    tmp = heartbeat_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(asdict(rec), f)
    os.replace(tmp, heartbeat_path)


def _read_heartbeat(path: str) -> HeartbeatRecord | None:
    try:
        with open(path) as f:
            d = json.load(f)
        return HeartbeatRecord(**d)
    except Exception:
        return None


def _write_failure_evidence(evidence_path: str, rec: HeartbeatRecord, reason: str) -> None:
    evidence = {
        "reason": reason,
        "pid": rec.pid,
        "game_uid": rec.game_uid,
        "last_heartbeat_utc": rec.last_heartbeat_utc,
        "detected_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "watchdog_action": "SIGTERM",
    }
    with open(evidence_path, "w") as f:
        json.dump(evidence, f, indent=2)


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
from agent.reliability.watchdog import run_watchdog
run_watchdog({heartbeat_path!r}, {evidence_path!r}, threshold_s={threshold_s!r})
"""
    return subprocess.Popen([sys.executable, "-c", script])
