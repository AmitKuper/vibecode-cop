"""Cryptographic signing, verification, and commitment for MCP messages."""

import hashlib
import hmac
import json
import logging
import secrets
from typing import Any

logger = logging.getLogger(__name__)


def canonical_json(obj: Any) -> str:
    """Serialize to canonical JSON (sorted keys, compact spacing).

    Args:
        obj: Object to serialize.

    Returns:
        Canonical JSON string.

    Raises:
        ValueError: If obj is not JSON-serializable.
    """
    try:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Object not JSON-serializable: {e}") from e


def sign_message(message_dict: dict, secret: str) -> str:
    """Sign a message using HMAC-SHA256.

    Args:
        message_dict: Message to sign (will be canonicalized).
        secret: Shared secret for HMAC.

    Returns:
        Hex-encoded HMAC signature.
    """
    canonical = canonical_json(message_dict)
    signature = hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    logger.debug(f"Signed message: {signature[:16]}...")
    return signature


def verify_signature(message_dict: dict, signature: str, secret: str) -> bool:
    """Verify a message signature.

    Args:
        message_dict: Message to verify.
        signature: Hex-encoded HMAC signature.
        secret: Shared secret for HMAC.

    Returns:
        True if signature is valid, False otherwise.
    """
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
    intent: str,  # "truth" or "lie"
    gamelet: int = 1,
) -> tuple[str, str]:
    """Create a commitment hash and return nonce.

    Args:
        game_id: Game identifier.
        step: Step/turn number.
        role: "cop" or "thief".
        state_hash: Hash of game state before move.
        move: "N", "S", "E", "W", or "STAY".
        hint: Optional hint text.
        intent: "truth" or "lie" (for hint).
        gamelet: Gamelet number within the series (1-based).

    Returns:
        (h_commit, nonce) where h_commit is the commitment hash.
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
    """Verify a commitment hash against revealed values.

    Args:
        h_commit: Original commitment hash.
        game_id: Game identifier.
        step: Step/turn number.
        role: "cop" or "thief".
        state_hash: Hash of game state before move.
        move: "N", "S", "E", "W", or "STAY".
        hint: Optional hint text.
        intent: "truth" or "lie".
        nonce: Nonce from revelation.
        gamelet: Gamelet number within the series (1-based).

    Returns:
        True if commitment matches, False otherwise.
    """
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
            f"Commitment mismatch: expected {h_commit[:16]}..., "
            f"got {computed_hash[:16]}..."
        )
    return is_valid


def hash_game_state(board_state: dict) -> str:
    """Hash game state for commitment.

    Args:
        board_state: Board state dict (cop_position, thief_position, turn, etc).

    Returns:
        SHA-256 hex hash of canonical JSON.
    """
    canonical = canonical_json(board_state)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
