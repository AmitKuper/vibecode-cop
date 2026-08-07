"""Internal MCP server tools for cop_worker — 6 tools callable by LeagueManager."""

from __future__ import annotations

import logging

from cop_worker.gamelet import Gamelet, GameletError
from cop_worker.synthetic_belief import SyntheticBeliefProvider

logger = logging.getLogger(__name__)

# Registry: (game_uid, sub_game_number) -> Gamelet
_GAMELETS: dict[tuple[str, int], Gamelet] = {}


def _key(game_uid: str, sub_game_number: int) -> tuple[str, int]:
    """Build registry key from game identity."""
    return (game_uid, sub_game_number)


def start_gamelet(
    game_uid: str,
    sub_game_number: int,
    terms: dict,
    opponent_group: str,
    role: str,
) -> dict:
    """Create and initialise a new gamelet.

    Args:
        game_uid: Canonical series identity.
        sub_game_number: Sub-game index 1..6.
        terms: Full agreed terms dict.
        opponent_group: Opponent's group_id.
        role: This worker's role ('police' for cop_worker).

    Returns:
        {'ok': True} on success.

    Raises:
        GameletError: If game_uid+sub_game_number already exists or terms invalid.
    """
    k = _key(game_uid, sub_game_number)
    if k in _GAMELETS:
        raise GameletError(f"Gamelet already exists: {game_uid} sg{sub_game_number}")
    g = Gamelet(
        game_uid=game_uid,
        sub_game_number=sub_game_number,
        terms=terms,
        opponent_group=opponent_group,
        role=role,
        belief_provider=SyntheticBeliefProvider(),
    )
    _GAMELETS[k] = g
    logger.info("start_gamelet %s sg%d role=%s", game_uid[:8], sub_game_number, role)
    return {"ok": True}


def deliver_event(
    game_uid: str,
    sub_game_number: int,
    event_type: str,
    payload: dict,
) -> dict:
    """Deliver an inbound event to the active gamelet.

    Args:
        game_uid: Canonical series identity.
        sub_game_number: Sub-game index.
        event_type: 'opponent_turn' | 'opponent_audit' | 'control_signal'.
        payload: Normalised domain object from LM.

    Returns:
        Dict with 'ok', 'response_payload', and 'state'.
    """
    g = _get(game_uid, sub_game_number)
    return g.process_event(event_type, payload)


def get_status(game_uid: str, sub_game_number: int) -> dict:
    """Return current gamelet status.

    Args:
        game_uid: Canonical series identity.
        sub_game_number: Sub-game index.

    Returns:
        Dict with game_uid, sub_game_number, state, step, role,
        and optionally commit_reveal_state if PLAYING.
    """
    g = _get(game_uid, sub_game_number)
    status = {
        "game_uid": game_uid,
        "sub_game_number": sub_game_number,
        "state": g.state,
        "step": g._step,
        "role": g.role,
    }
    if g._cr is not None:
        status["commit_reveal_state"] = g._cr.state
    return status


def prepare_audit(game_uid: str, sub_game_number: int) -> dict:
    """Prepare the local audit bundle. Transitions GAMEPLAY_TERMINAL -> AUDITING.

    Args:
        game_uid: Canonical series identity.
        sub_game_number: Sub-game index.

    Returns:
        Dict with 'ok' and 'audit_bundle'.
    """
    g = _get(game_uid, sub_game_number)
    return g.prepare_audit()


def get_result(game_uid: str, sub_game_number: int) -> dict:
    """Return sanitised settlement summary. Only after SETTLED.

    Args:
        game_uid: Canonical series identity.
        sub_game_number: Sub-game index.

    Returns:
        Dict with result fields (no raw nonces).
    """
    g = _get(game_uid, sub_game_number)
    return g.get_result()


def shutdown_gamelet(game_uid: str, sub_game_number: int) -> dict:
    """Gracefully shut down a gamelet and remove it from the registry.

    Args:
        game_uid: Canonical series identity.
        sub_game_number: Sub-game index.

    Returns:
        Dict with 'ok' and 'final_state'.
    """
    g = _get(game_uid, sub_game_number)
    result = g.shutdown()
    del _GAMELETS[_key(game_uid, sub_game_number)]
    return result


def _get(game_uid: str, sub_game_number: int) -> Gamelet:
    """Retrieve gamelet by identity, raising GameletError if not found.

    Args:
        game_uid: Canonical series identity.
        sub_game_number: Sub-game index.

    Raises:
        GameletError: If no gamelet is registered for the given identity.
    """
    k = _key(game_uid, sub_game_number)
    if k not in _GAMELETS:
        raise GameletError(f"No gamelet found: {game_uid} sg{sub_game_number}")
    return _GAMELETS[k]


def clear_all_gamelets() -> None:
    """Clear all gamelets (for test teardown only)."""
    _GAMELETS.clear()
