"""In-process ref-v3 wrappers — same message format as HTTP, direct call."""

from __future__ import annotations

from ref3_selfplay.runtime import TERMS


def _ip_start_gamelet(ms, game_uid: str, sg: int, role: str) -> dict:
    """Call start_gamelet on an in-process mcp_server module.

    Args:
        ms: cop_worker.mcp_server or thief_worker.mcp_server module.
        game_uid: Series identity.
        sg: Sub-game number.
        role: 'police' or 'thief'.

    Returns:
        {'ok': True} on success.
    """
    return ms.start_gamelet(
        game_uid=game_uid,
        sub_game_number=sg,
        terms=TERMS,
        opponent_group="ref3_peer",
        role=role,
    )


def _ip_start_playing(ms, game_uid: str, sg: int) -> dict:
    """Transition gamelet to PLAYING state.

    Args:
        ms: mcp_server module.
        game_uid: Series identity.
        sg: Sub-game number.

    Returns:
        {'ok': True, 'state': 'PLAYING'}.
    """
    return ms.start_playing(game_uid, sg)


def _ip_deliver_commit(ms, game_uid: str, sg: int, step: int, commitment_hash: str) -> dict:
    """Deliver an opponent commit event (ref-v3 wire format).

    Args:
        ms: mcp_server module.
        game_uid: Series identity.
        sg: Sub-game number.
        step: Current step number.
        commitment_hash: Opponent's commitment hash.

    Returns:
        Response dict with our commitment in response_payload.
    """
    return ms.deliver_event(
        game_uid=game_uid,
        sub_game_number=sg,
        event_type="opponent_turn",
        payload={
            "step": step,
            "kind": "commit",
            "commitment_hash": commitment_hash,
            "nonce": None,
            "action": None,
        },
    )


def _ip_shutdown(ms, game_uid: str, sg: int) -> dict:
    """Shutdown a gamelet.

    Args:
        ms: mcp_server module.
        game_uid: Series identity.
        sg: Sub-game number.

    Returns:
        Shutdown result dict.
    """
    return ms.shutdown_gamelet(game_uid, sg)
