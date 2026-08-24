"""The sub-game turn loop: mover lifecycle, sealed turns, concessions, audit submission.

Call-site pins live HERE (tests read _run_turns's source): mover construction+reset
before the loop, barrier tracking + rule-46/47 self-check inside it, audit after it.
"""

from __future__ import annotations

import secrets

from ref3_match import gui_context
from ref3_match.match_log import _log_peer_scent_model
from ref3_match.mover import RLMover
from ref3_match.net import _latest_turn, _poll_turn
from ref3_match.runtime_cfg import _t
from ref3_match.subgame_moves import (
    _absorb_inbound_caught,  # noqa: F401  (facade re-export)
    _compose_and_send_turn,
    _prep_claim_answer,
    _send_done_control,
)
from ref3_match.turns_inbound import cop_inbound, result_claim  # noqa: F401  (re-export)
from ref3_match.wire import _from_wire_cell, _to_wire_cell


async def _run_turns(
    out_session,
    in_session,
    *,
    role: str,
    sub_game: int,
    terms: dict,
    scent_model: str,
    move_policy: str,
):
    """Play the sub-game's turns; returns (mover, rl_moves, captured, disputed, caught_cell)."""
    from cop_worker.language.deception_policy import NaturalLanguagePolicy
    from cop_worker.protocol.reference_v3 import build_turn

    max_steps = terms["max_steps"]
    mover = RLMover(role, terms, scent_model=scent_model, move_policy=move_policy)
    # One sub-game == one episode: without this the GRU hidden state carried over from
    # the PREVIOUS sub-game (every match we played, counted included). Training always
    # resets between episodes; serving never did.
    mover.policy.reset()
    # Template-only hint policy: provably irrelevant to play (local_obs_to_tensor never
    # reads last_hint); intent is chosen independently of movement and may lie.
    nlp = NaturalLanguagePolicy(role="cop" if role == "police" else "thief")
    we_move_first = role == "thief"  # reference-v3: THIEF moves first every sub-game
    rl_moves: list[str] = []
    pending_answer: dict | None = None  # thief's answer to a cop capture_claim (rides next turn)
    captured = False  # True if this sub-game ended in a capture (either direction)
    our_last_claim: list[int] | None = None  # cop: the cell our last capture_claim named
    disputed_capture: dict | None = None  # a caught=true we could NOT corroborate (audit note)
    settled_caught_cell: list[int] | None = None  # the cell a caught=true settled on

    for step in range(1, max_steps + 1):
        if not we_move_first:
            # cop: wait for the thief's sealed turn first, absorb its scent/hint
            # (turns_inbound.cop_inbound: caught settlement + survival terminal).
            opp, ended, cell, disputed = await cop_inbound(
                in_session, mover, our_last_claim, sub_game, step
            )
            if ended == "captured":
                settled_caught_cell, disputed_capture, captured = cell, disputed, True
                break
            if ended == "survival":
                break
        else:
            # Thief moves FIRST: at round r the cop's newest turn is numbered r-1
            # (per-sender numbering) — absorb that one, or the thief plays blind.
            opp = _latest_turn(in_session, step - 1) if step > 1 else {}
        gui_context.note_received(opp, step)
        opp_hint = opp.get("hint", "")
        opp_smell = opp.get("smell_grid", {})
        # Log-only diagnostic: which registered scent_model is the peer actually transmitting?
        _log_peer_scent_model(sub_game, step, opp_smell, ours=scent_model)
        action = mover.decide(step, sub_game, opp_smell, opp_hint)
        rl_moves.append(action)
        mover.apply(action)
        gui_context.note_sent(out_session)
        # Profile the opponent's language; no trust verdict during play (their move
        # stays sealed until the audit — the trust model holds at its 0.5 default).
        if opp_hint:
            nlp.record_opponent_hint(opp_hint)
        answer, pending_answer = pending_answer, None
        caught, win_claim, claim_cell = await _compose_and_send_turn(
            out_session,
            mover,
            nlp,
            role=role,
            sub_game=sub_game,
            step=step,
            max_steps=max_steps,
            terms=terms,
            action=action,
            answer=answer,
        )
        if claim_cell is not None:
            our_last_claim = claim_cell
        if caught:
            print(f"[match] sg{sub_game} our thief answered caught=true at step {step}")
            captured = True
            break
        if we_move_first and win_claim is None:
            # Thief waits for the cop's turn; any capture claim it carries is answered
            # on our next turn.
            await _poll_turn(
                in_session.turns, step, timeout=_t("turn_poll_sec", 120.0), session=in_session
            )
            cop_turn = _latest_turn(in_session, step)
            pending_answer = _prep_claim_answer(cop_turn, mover) or pending_answer
            # Track the cop's barrier and run the rule-46/47 self-check on the board it
            # just changed. An ending only we can see must be SAID: the concession is a
            # real STAY turn whose field advances; it supersedes any pending answer.
            mover.observe_peer_barrier(_from_wire_cell(cop_turn.get("barrier_placed")))
            rule = mover.self_capture_check()
            if rule is not None:
                final_step = step + 1
                concession = {"claim": _to_wire_cell(mover.pos), "caught": True}
                final_payload = {
                    "step": final_step,
                    "role": role,
                    "sub_game": sub_game,
                    "position": _to_wire_cell(mover.pos),
                    "move": "STAY",
                    "intent": "truth",
                }
                final_nonce = secrets.token_hex(16)
                final_turn, final_record = build_turn(
                    record_payload=final_payload,
                    nonce=final_nonce,
                    sender=role,
                    hint="",
                    smell_grid=mover.our_smell_grid(),
                    barrier_placed=None,
                    claim_response=concession,
                    win_claim=None,
                )
                await out_session.send_turn(final_turn, final_record)
                print(
                    f"[match] sg{sub_game} thief self-detected {rule} capture at "
                    f"step {step} — conceding (cell {mover.pos})"
                )
                captured = True
                break

    await out_session.send_audit(role, result_claim(captured))
    await _send_done_control(out_session, role, sub_game, max_steps)
    return mover, rl_moves, captured, disputed_capture, settled_caught_cell
