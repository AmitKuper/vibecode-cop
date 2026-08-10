"""Gamelet-registry read/lifecycle operations for the worker MCP server."""

from __future__ import annotations

import logging

from cop_worker import mcp_server as _srv
from cop_worker.mcp_server import _get, _key

logger = logging.getLogger(__name__)


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
    del _srv._GAMELETS[_key(game_uid, sub_game_number)]
    return result
