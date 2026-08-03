"""Cryptographic signing, verification, and commitment for MCP messages."""

import hashlib
import hmac
import json
import logging
import secrets
from typing import Any

logger = logging.getLogger(__name__)


def canonical_json(obj: Any) -> str:
    """Serialize to canonical JSON (sorted keys, compact spacing)."""
    try:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Object not JSON-serializable: {e}") from e


def sign_message(message_dict: dict, secret: str) -> str:
    """HMAC-SHA256 sign a message dict. Returns hex digest."""
    canonical = canonical_json(message_dict)
    signature = hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    logger.debug(f"Signed message: {signature[:16]}...")
    return signature


def verify_signature(message_dict: dict, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature. Returns True if valid."""
    expected = sign_message(message_dict, secret)
    is_valid = hmac.compare_digest(signature, expected)
    if not is_valid:
        logger.warning(f"Signature mismatch: expected {expected[:16]}..., got {signature[:16]}...")
    return is_valid


def create_commitment(
    game_id: str,
    step: int,
    role: str,
    state_hash: str,
    move: str,
    hint: str,
    intent: str,
    gamelet: int = 1,
) -> tuple[str, str]:
    """Create a commitment hash. Returns (h_commit, nonce).

    h_commit = SHA-256(canonical_json({game_id, gamelet, step, role,
               state_hash, move, hint, intent, nonce}))
    Nonce is withheld from opponent until final_audit.
    """
    nonce = secrets.token_hex(32)
    commit_payload = {
        "game_id": game_id,
        "gamelet": gamelet,
        "step": step,
        "role": role,
        "state_hash": state_hash,
        "move": move,
        "hint": hint,
        "intent": intent,
        "nonce": nonce,
    }
    canonical = canonical_json(commit_payload)
    h_commit = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    logger.debug(f"Created commitment: {h_commit[:16]}... (nonce: {nonce[:16]}...)")
    return h_commit, nonce


def verify_commitment(
    h_commit: str,
    game_id: str,
    step: int,
    role: str,
    state_hash: str,
    move: str,
    hint: str,
    intent: str,
    nonce: str,
    gamelet: int = 1,
) -> bool:
    """Verify a commitment hash against revealed values. Returns True if valid."""
    commit_payload = {
        "game_id": game_id,
        "gamelet": gamelet,
        "step": step,
        "role": role,
        "state_hash": state_hash,
        "move": move,
        "hint": hint,
        "intent": intent,
        "nonce": nonce,
    }
    canonical = canonical_json(commit_payload)
    computed_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    is_valid = computed_hash == h_commit
    if not is_valid:
        logger.warning(
            f"Commitment mismatch: expected {h_commit[:16]}..., got {computed_hash[:16]}..."
        )
    return is_valid


def hash_game_state(board_state: dict) -> str:
    """Hash game state for commitment. Returns SHA-256 hex of canonical JSON."""
    canonical = canonical_json(board_state)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def public_transition_hash(
    game_id: str,
    gamelet: int,
    step: int,
    config_sha256: str,
    barriers: list,
    cop_barriers_remaining: int,
    previous_transcript_root: str,
) -> str:
    """Hash public (non-private) transition data for cross-peer verification.

    This hash covers only information that BOTH peers can independently verify
    without revealing private position knowledge. It is included in audit logs
    and can be exchanged between peers to confirm they share the same game history.

    Args:
        game_id: Unique game identifier.
        gamelet: Gamelet number within the series.
        step: Turn number.
        config_sha256: SHA-256 of the agreed canonical config.
        barriers: List of barrier positions (will be sorted for determinism).
        cop_barriers_remaining: Remaining barrier budget for cop.
        previous_transcript_root: Hash of the previous step's public state (or '' for step 0).

    Returns:
        64-char hex SHA-256 string.
    """
    payload = {
        "game_id": game_id,
        "gamelet": gamelet,
        "step": step,
        "config_sha256": config_sha256,
        "barriers": sorted(barriers),
        "cop_barriers_remaining": cop_barriers_remaining,
        "previous_transcript_root": previous_transcript_root,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
