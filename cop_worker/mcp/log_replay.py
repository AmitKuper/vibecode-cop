"""Log reading, replay, and tamper-detection utilities for MCP game logs."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_from_file(log_file: Path) -> list[dict]:
    """Load events from JSONL file."""
    events = []
    try:
        with open(log_file, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
    except OSError as e:
        logger.warning(f"Failed to load game log: {e}")
    return events


def load_log_json(log_file: Path) -> dict:
    """Load a structured log_{game_id}_g{NN}.json file."""
    with open(log_file, encoding="utf-8") as f:
        return json.load(f)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_of_file(path: Path) -> str:
    """Return SHA-256 of file contents (raw bytes)."""
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def sha256_of_json(obj: dict) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def verify_log_integrity(log_file: Path, expected_hash: str | None = None) -> dict:
    """Verify log file has not been tampered with.

    Args:
        log_file: Path to the log JSON file.
        expected_hash: If provided, compare SHA-256 of file contents against this.

    Returns:
        Dict with keys: ok (bool), log_sha256 (str), hash_match (bool | None), details (str).
    """
    if not log_file.exists():
        return {"ok": False, "details": f"Log file not found: {log_file}"}

    log_sha256 = sha256_of_file(log_file)
    hash_match = None
    if expected_hash is not None:
        hash_match = hmac_equal(log_sha256, expected_hash)

    return {
        "ok": hash_match is not False,
        "log_sha256": log_sha256,
        "hash_match": hash_match,
        "details": "ok" if hash_match is not False else "sha256 mismatch — log may be tampered",
    }


def hmac_equal(a: str, b: str) -> bool:
    import hmac as _hmac

    return _hmac.compare_digest(a.lower(), b.lower())


def audit_log_commitments(log_data: dict) -> dict:
    """Verify every commitment in a structured game log.

    For each step in log_data["entries"], verify that h_commit ==
    SHA-256(canonical_json({game_id, gamelet, step, role, state_hash, move,
    hint, intent, nonce})) — but only if all reveal fields are present.

    Returns:
        Dict with keys: ok (bool), verified (int), failed (int), skipped (int), details (list).
    """
    from cop_worker.crypto import verify_commitment

    game_id = log_data.get("game_id", "")
    gamelet_str = log_data.get("game_number", "01")
    try:
        gamelet = int(gamelet_str.lstrip("g") if isinstance(gamelet_str, str) else gamelet_str)
    except (ValueError, AttributeError):
        gamelet = 1

    entries = log_data.get("entries", [])
    verified = failed = skipped = 0
    details = []

    for entry in entries:
        step = entry.get("step")
        for role in ("cop", "thief"):
            h_commit = entry.get(f"{role}_h_commit")
            move = entry.get(f"{role}_move")
            state_hash = entry.get(f"{role}_state_hash")

            # Skip entries missing commitment data (pre-reveal or partial logs)
            if not h_commit or not move:
                skipped += 1
                continue

            # We can only verify if the nonce was stored (final_audit revealed it)
            nonce = entry.get(f"{role}_nonce")
            if not nonce:
                skipped += 1
                continue

            ok = verify_commitment(
                h_commit=h_commit,
                game_id=game_id,
                step=step,
                role=role,
                state_hash=state_hash or "",
                move=move,
                hint=entry.get(f"{role}_hint", ""),
                intent=entry.get(f"{role}_intent", "truth"),
                nonce=nonce,
                gamelet=gamelet,
            )
            if ok:
                verified += 1
                details.append({"step": step, "role": role, "result": "ok"})
            else:
                failed += 1
                details.append({"step": step, "role": role, "result": "commitment_mismatch"})
                logger.warning(f"[Replay] Commitment mismatch: step={step} role={role}")

    return {
        "ok": failed == 0 and verified > 0,
        "verified": verified,
        "failed": failed,
        "skipped": skipped,
        "details": details,
    }
