"""Peer-side final audit: each agent verifies the opponent's commitments locally.

No central judge is involved. Each agent independently checks every nonce
revealed by the opponent against the h_commit values it stored at the time
of commitment exchange.
"""

import json
import logging
import os
from pathlib import Path

from agent.mcp.crypto import verify_commitment

logger = logging.getLogger(__name__)


def _load_unique_object(path: Path) -> dict:
    """Load a JSON object while rejecting duplicate keys."""

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate evidence key {key!r} in {path.name}")
            result[key] = value
        return result

    with open(path, encoding="utf-8") as handle:
        value = json.load(handle, object_pairs_hook=reject_duplicates)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _atomic_write_object(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def load_opponent_commits(game_dir: Path) -> dict[int, str]:
    """Return {step: h_commit} from disk, empty dict if file missing."""
    path = game_dir / "opponent_commitments.json"
    if not path.exists():
        logger.warning(f"opponent_commitments.json missing in {game_dir}")
        return {}
    raw = _load_unique_object(path)
    return {int(k): v for k, v in raw.items()}


def load_my_reveals(game_dir: Path, role: str) -> dict[int, dict]:
    """Return {step: reveal_dict} from disk, empty dict if file missing."""
    path = game_dir / "opponent_reveals.json"
    if not path.exists():
        logger.warning(f"opponent_reveals.json missing in {game_dir}")
        return {}
    raw = _load_unique_object(path)
    return {int(k): v for k, v in raw.items()}


def verify_opponent_reveal(
    h_commit: str,
    reveal: dict,
    game_id: str,
    step: int,
    opponent_role: str,
    gamelet: int,
) -> bool:
    """Verify a single opponent reveal against its stored h_commit."""
    return verify_commitment(
        h_commit=h_commit,
        game_id=game_id,
        step=step,
        role=opponent_role,
        state_hash=reveal.get("state_hash", ""),
        move=reveal.get("move", ""),
        hint=reveal.get("hint", ""),
        intent=reveal.get("intent", ""),
        nonce=reveal.get("nonce", ""),
        gamelet=gamelet,
    )


def run_final_audit(
    game_dir: Path,
    game_id: str,
    opponent_role: str,
    opponent_nonces: dict[int, str],
    *,
    gamelet: int,
    authoritative_final_step: int,
) -> tuple[bool, dict]:
    """Verify all opponent commitments against revealed nonces locally.

    Returns (audit_ok, details) where details maps step -> "ok" | error string.
    """
    try:
        h_commits = load_opponent_commits(game_dir)
        reveals = load_my_reveals(game_dir, opponent_role)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return False, {"audit_status": "FAILED", "note": f"invalid evidence: {exc}"}

    # A zero-turn abort produced no commitments — NOT_APPLICABLE, never a counted result.
    if authoritative_final_step == 0 and not h_commits and not reveals and not opponent_nonces:
        logger.warning(f"[PeerAudit] {game_id}: no opponent commits — NOT_APPLICABLE")
        return False, {
            "audit_status": "NOT_APPLICABLE",
            "note": "zero-turn abort; not a counted match",
        }

    if authoritative_final_step < 1:
        return False, {
            "audit_status": "FAILED",
            "note": "authoritative final step must be positive for a counted gamelet",
        }

    # Exact evidence-set check: every step from 1..final_step must be present,
    # with no gaps, no extras, and no non-contiguous steps.
    final_step = authoritative_final_step
    expected = set(range(1, final_step + 1))
    if set(h_commits.keys()) != expected:
        missing = expected - set(h_commits.keys())
        extra = set(h_commits.keys()) - expected
        logger.warning(f"[PeerAudit] Commitment step mismatch: missing={missing} extra={extra}")
        return False, {
            "audit_status": "FAILED",
            "note": f"commitment steps do not form contiguous range 1..{final_step}",
        }
    if set(reveals.keys()) != expected:
        return False, {
            "audit_status": "FAILED",
            "note": f"reveal steps do not match commitment steps 1..{final_step}",
        }
    if set(opponent_nonces.keys()) != expected:
        return False, {
            "audit_status": "FAILED",
            "note": f"nonce steps do not match commitment steps 1..{final_step}",
        }

    verified = failed = 0
    details: dict[str, str] = {}

    for step in range(1, final_step + 1):
        h_commit = h_commits[step]
        nonce = opponent_nonces.get(step)
        reveal = reveals.get(step)
        if nonce is None:
            details[f"step_{step}"] = "missing_nonce"
            failed += 1
            logger.warning(f"[PeerAudit] Missing nonce for step {step}")
            continue
        if reveal is None:
            details[f"step_{step}"] = "missing_reveal"
            failed += 1
            logger.warning(f"[PeerAudit] Missing reveal for step {step}")
            continue
        reveal_with_nonce = {**reveal, "nonce": nonce}
        ok = verify_opponent_reveal(
            h_commit, reveal_with_nonce, game_id, step, opponent_role, gamelet
        )
        if ok:
            verified += 1
            details[f"step_{step}"] = "ok"
        else:
            failed += 1
            details[f"step_{step}"] = "commitment_mismatch"
            logger.warning(f"[PeerAudit] Commitment mismatch at step {step} for {opponent_role}")

    audit_ok = failed == 0
    details["audit_status"] = "PASSED" if audit_ok else "FAILED"
    logger.info(
        f"[PeerAudit] {game_id}: {verified} verified, {failed} failed (opp={opponent_role})"
    )
    return audit_ok, details


def append_opponent_commit(game_dir: Path, step: int, h_commit: str) -> None:
    """Persist one opponent h_commit to disk (called after receiving COMMIT)."""
    path = game_dir / "opponent_commitments.json"
    existing: dict = {}
    if path.exists():
        existing = _load_unique_object(path)
    prior = existing.get(str(step))
    if prior is not None:
        if prior == h_commit:
            return
        raise ValueError(f"conflicting commitment replay at step {step}")
    if step != len(existing) + 1:
        raise ValueError(f"commitment step must be contiguous: got {step}")
    existing[str(step)] = h_commit
    _atomic_write_object(path, existing)


def append_opponent_reveal(game_dir: Path, step: int, reveal: dict) -> None:
    """Persist one opponent reveal dict to disk (called after receiving REVEAL)."""
    path = game_dir / "opponent_reveals.json"
    existing: dict = {}
    if path.exists():
        existing = _load_unique_object(path)
    prior = existing.get(str(step))
    if prior is not None:
        if prior == reveal:
            return
        raise ValueError(f"conflicting reveal replay at step {step}")
    if step != len(existing) + 1:
        raise ValueError(f"reveal step must be contiguous: got {step}")
    existing[str(step)] = reveal
    _atomic_write_object(path, existing)
