"""One sub-game over the reference-v3 wire: handshake → turns → settlement."""

from __future__ import annotations

from ref3_match.subgame_settle import _settle
from ref3_match.subgame_setup import _handshake
from ref3_match.subgame_turns import _run_turns


async def _play_subgame(
    out_session,
    in_session,
    *,
    role: str,
    sub_game: int,
    group_id: str,
    group_name: str,
    terms: dict,
    opponent_group_hint: str,
    members: list | None = None,
    our_counted: int = 0,
    scent_model: str = "multiplicative_book_v1",
    move_policy: str = "rl",
    declared_opponent_group: str | None = None,
) -> dict:
    """Drive one full sub-game; returns the settled result row (see _settle)."""
    hs = await _handshake(
        out_session,
        in_session,
        role=role,
        sub_game=sub_game,
        group_id=group_id,
        group_name=group_name,
        terms=terms,
        members=members,
        our_counted=our_counted,
        scent_model=scent_model,
        declared_opponent_group=declared_opponent_group,
    )
    _mover, rl_moves, captured, disputed, caught_cell = await _run_turns(
        out_session,
        in_session,
        role=role,
        sub_game=sub_game,
        terms=terms,
        scent_model=scent_model,
        move_policy=move_policy,
    )
    return await _settle(
        out_session,
        in_session,
        role=role,
        sub_game=sub_game,
        hs=hs,
        opponent_group_hint=opponent_group_hint,
        rl_moves=rl_moves,
        captured=captured,
        disputed_capture=disputed,
        settled_caught_cell=caught_cell,
    )
