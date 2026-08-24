"""Cop-side inbound handling for the turn loop (split from subgame_turns)."""

from __future__ import annotations

from ref3_match.net import _latest_turn, _poll_turn
from ref3_match.runtime_cfg import _t
from ref3_match.subgame_moves import _absorb_inbound_caught


def result_claim(captured: bool) -> str:
    """How the GAME ended, not how the exchange ended.

    With no capture the thief survived the step limit, so BOTH roles claim
    "survival" — which is what our own result rows and filed report already say.
    We used to claim "timeout" here (true of the wire, false of the game): it
    contradicted our own result and made peers who dispute contradicted endings
    record mutual_agreement=false while ours said true (najamjad, 2026-08-14).
    """
    return "capture" if captured else "survival"


async def cop_inbound(in_session, mover, our_last_claim, sub_game: int, step: int):
    """Wait for the thief's sealed turn, absorb it; returns (opp, ended, cell, disputed).

    ``ended`` is "captured" when a caught=true settled, "survival" when the
    thief declared the survival terminal on its final step (settled before the
    cop moves — a post-terminal cop move could write a capture-shaped record
    into a settled survival, anrbj666's flagged wart), else None.
    """
    await _poll_turn(in_session.turns, step, timeout=_t("turn_poll_sec", 120.0), session=in_session)
    opp = _latest_turn(in_session, step)
    cell, disputed, done = _absorb_inbound_caught(opp, mover, our_last_claim, sub_game, step)
    if done:
        return opp, "captured", cell, disputed
    if (opp.get("win_claim") or {}).get("type") == "survival":
        print(
            f"[match] sg{sub_game} thief declared survival terminal at step {step}; "
            f"cop stops (no post-terminal move)"
        )
        return opp, "survival", None, None
    return opp, None, None, None
