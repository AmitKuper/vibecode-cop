"""State/transition hashing: public roots, private commitments, protocol hash."""

import hashlib
import json
import logging
from typing import Any

from cop_worker.crypto import canonical_json

logger = logging.getLogger(__name__)


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
