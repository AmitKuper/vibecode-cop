"""Internal MCP server tools for cop_worker — 6 tools callable by LeagueManager."""

from __future__ import annotations

import logging
from pathlib import Path

from cop_worker.gamelet import Gamelet, GameletError
from cop_worker.synthetic_belief import SyntheticBeliefProvider

logger = logging.getLogger(__name__)

# Registry: (game_uid, sub_game_number) -> Gamelet
_GAMELETS: dict[tuple[str, int], Gamelet] = {}

# Module-level RL policy (None if load failed)
_POLICY = None


def _load_policy():
    """Attempt to load the cop RL policy from models/MANIFEST.json.

    Sets module-level _POLICY on success; logs and leaves None on failure.
    """
    global _POLICY
    try:
        from cop_worker.rl.recurrent_policy import load_recurrent_policy

        manifest = Path(__file__).parent.parent / "models" / "MANIFEST.json"
        _POLICY = load_recurrent_policy(manifest, "cop")
        logger.info("RL cop policy loaded from %s", manifest)
    except Exception as exc:
        logger.warning("RL cop policy not loaded (random fallback active): %s", exc)
        _POLICY = None


_load_policy()


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
        policy=_POLICY,
    )
    _GAMELETS[k] = g
    logger.info("start_gamelet %s sg%d role=%s", game_uid[:8], sub_game_number, role)
    return {"ok": True}


def start_playing(game_uid: str, sub_game_number: int) -> dict:
    """Transition the gamelet from LOCKED to PLAYING state.

    Args:
        game_uid: Canonical series identity.
        sub_game_number: Sub-game index.

    Returns:
        {'ok': True, 'state': 'PLAYING'} on success.
    """
    g = _get(game_uid, sub_game_number)
    g.start_playing()
    # One sub-game == one episode. Every gamelet shares the module-level _POLICY, so without
    # this the GRU hidden state (and the scent decoder's previous-frame memory) carried from
    # the previous sub-game into a board that had just been reset. Training always resets
    # between episodes; serving never did. Resetting here rather than in start_gamelet ties it
    # to the moment play actually begins. NOTE: this assumes reference-v3's sequential
    # sub-games -- a shared recurrent policy cannot serve two gamelets concurrently.
    if _POLICY is not None and hasattr(_POLICY, "reset"):
        _POLICY.reset()
    logger.info("start_playing %s sg%d", game_uid[:8], sub_game_number)
    return {"ok": True, "state": g.state}


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


from cop_worker.mcp_server_ops import (  # noqa: E402,F401  (re-exports)
    deliver_event,
    get_result,
    get_status,
    prepare_audit,
    shutdown_gamelet,
)
