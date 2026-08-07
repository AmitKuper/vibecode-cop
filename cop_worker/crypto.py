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
    nonce: str | None = None,
) -> tuple[str, str]:
    """Create a commitment hash. Returns (h_commit, nonce).

    h_commit = SHA-256(canonical_json({game_id, gamelet, step, role,
               state_hash, move, hint, intent, nonce}))
    Nonce is withheld from opponent until final_audit.
    """
    nonce = nonce or secrets.token_hex(32)
    if len(nonce) < 32:
        raise ValueError("commitment nonce must contain at least 128 bits")
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


def build_public_transition_root(
    game_uid: str,
    gamelet: int,
    step: int,
    declaration_hash: str,
    config_hash: str,
    protocol_hash: str,
    public_barriers: list,
    cop_barriers_quota: int,
    revealed_cop_move: str,
    revealed_thief_move: str,
    previous_transcript_root: str,
    public_outcome: str = "",
) -> str:
    """SHA-256 of all public/agreed state after one step. Non-enumerable (large domain)."""
    payload = {
        "game_uid": game_uid,
        "gamelet": gamelet,
        "step": step,
        "declaration_hash": declaration_hash,
        "config_hash": config_hash,
        "protocol_hash": protocol_hash,
        "public_barriers": sorted(str(b) for b in public_barriers),
        "cop_barriers_quota": cop_barriers_quota,
        "revealed_cop_move": revealed_cop_move,
        "revealed_thief_move": revealed_thief_move,
        "previous_transcript_root": previous_transcript_root,
        "public_outcome": public_outcome,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def build_private_state_commitment(
    own_position: tuple,
    own_barriers_remaining: int,
    local_nonce: str,
    step: int,
    gamelet: int,
    game_uid: str,
) -> str:
    """Salted private local-state commitment. Salt = local_nonce (secret until audit).

    Binds own position without exposing it. Non-enumerable because nonce is 32 random bytes.
    Position alone would be enumerable in 7x7=49 cells; the nonce salt prevents that.
    """
    payload = {
        "game_uid": game_uid,
        "gamelet": gamelet,
        "step": step,
        "own_position": list(own_position),
        "own_barriers_remaining": own_barriers_remaining,
        "local_nonce": local_nonce,  # secret salt — never revealed until final audit
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


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


def build_commitment(nonce: str, action: dict) -> str:
    """Build a simple SHA256 commitment: SHA256(nonce + canonical_json(action)).

    Args:
        nonce: Secret nonce string (withheld until reveal phase).
        action: Action dict to commit to (e.g. {"type": "move", "direction": "N"}).

    Returns:
        64-char hex SHA256 digest.
    """
    action_json = json.dumps(action, sort_keys=True, separators=(",", ":"))
    data = (nonce + action_json).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical_domain_state_root(state: Any, config_sha256: str) -> str:
    """Commit to a complete canonical domain state for final-audit replay."""
    state_payload = state.model_dump(mode="json") if hasattr(state, "model_dump") else state
    return hashlib.sha256(
        canonical_json({"config_sha256": config_sha256, "state": state_payload}).encode("utf-8")
    ).hexdigest()


def combined_protocol_hash(*profile_hashes: str) -> str:
    """Order-independent binding for both peers' locked protocol profiles."""
    values = sorted(value for value in profile_hashes if value)
    if not values:
        return hashlib.sha256(b"native-protocol-profile-v1").hexdigest()
    return hashlib.sha256(canonical_json(values).encode("utf-8")).hexdigest()
