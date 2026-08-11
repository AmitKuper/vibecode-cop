"""Per-step move phases used by the turn loop: absorb inbound settle, compose our turn."""

from __future__ import annotations

import secrets

from ref3_match.wire import _corroborate_caught, _from_wire_cell, _to_wire_cell


def _absorb_inbound_caught(opp: dict, mover, our_last_claim, sub_game: int, step: int):
    """Handle a thief ``caught=true`` arriving on the cop's inbound turn.

    Returns (settled_caught_cell, disputed_capture, captured): captured is True only
    when the message actually settles this sub-game. A caught=true from the thief
    settles CAPTURE — but corroborate which KIND (SPEC §3.1): a cell echoing our last
    claim is an ANSWER (co-location); any other cell is a CONCESSION (rule 46/47) and
    must be captured under OUR OWN barrier record — never under the barrier list the
    thief reports. A failed corroboration still ends the game but is recorded as
    disputed, not clean.
    """
    _cr = opp.get("claim_response") or {}
    if _cr.get("caught") is not True:
        return None, None, False
    settled_caught_cell = None
    disputed_capture = None
    _cell = _cr.get("claim")  # wire [row, col]
    if isinstance(_cell, (list, tuple)) and len(_cell) == 2:
        settled_caught_cell = [int(_cell[0]), int(_cell[1])]  # keep wire form
    _kind, _clean = _corroborate_caught(
        _from_wire_cell(_cell) or _cell,
        our_last_claim,
        mover.barriers,
        mover.pos,
        mover.grid,
    )
    if not _clean:
        disputed_capture = {
            "cell": _cell,
            "kind": _kind,
            "our_claim": our_last_claim,
            "our_barriers": [list(b) for b in mover.barriers],
        }
        print(
            f"[match] sg{sub_game} step {step}: caught=true did NOT "
            f"corroborate ({_kind}, cell={_cell}) — recording disputed"
        )
    else:
        print(f"[match] sg{sub_game} thief conceded capture at step {step} ({_kind})")
    return settled_caught_cell, disputed_capture, True


def _prep_claim_answer(cop_turn: dict, mover) -> dict | None:
    """Prepare the thief's answer to a cop capture_claim (rides our next turn).

    Echo the asked cell verbatim (kit convention); compare in wire form
    (kit turnloop.py:271-273).
    """
    claim = cop_turn.get("capture_claim")  # wire [row, col]
    if claim is None:
        return None
    return {"claim": list(claim), "caught": list(claim) == _to_wire_cell(mover.pos)}


async def _send_done_control(out_session, role: str, sub_game: int, max_steps: int) -> None:
    """Best-effort end-of-sub-game control message (never blocks settlement)."""
    import contextlib

    with contextlib.suppress(Exception):
        await out_session.send_control(
            {
                "kind": "done",
                "sender": role,
                "sub_game_number": sub_game,
                "status": "complete",
                "step_budget": float(max_steps),
                "payload": {},
            }
        )


async def _compose_and_send_turn(
    out_session,
    mover,
    nlp,
    *,
    role: str,
    sub_game: int,
    step: int,
    max_steps: int,
    terms: dict,
    action: str,
    answer: dict | None,
):
    """Build, seal, and send our turn. Returns (caught, win_claim, our_last_claim)."""
    from cop_worker.protocol.reference_v3 import build_turn

    # Language is chosen independently of movement (the book's requirement) and may lie.
    intent = nlp.choose_intent(
        step=step,
        gamelet=sub_game,
        physical_action=action,
        token_budget=int(terms.get("hint_max_words", 15)),
    )
    hint_text = nlp.generate(action, intent)
    # Hard clamp to the negotiated word cap: validate_turn rejects a longer hint outright,
    # and a counted series is one-shot — never risk it on template wording.
    _cap = int(terms.get("hint_max_words", 15))
    if len(hint_text.split()) > _cap:
        hint_text = " ".join(hint_text.split()[:_cap])
    record_payload = {
        "step": step,
        "role": role,
        "sub_game": sub_game,
        "position": _to_wire_cell(mover.pos),
        "move": action,
        "intent": intent.value,
    }
    if mover.last_barrier is not None:
        record_payload["barrier_placed"] = _to_wire_cell(mover.last_barrier)
    # A pending capture-claim answer (thief only) rides this turn; caught => terminal.
    caught = bool(answer and answer.get("caught"))
    step_nonce = secrets.token_hex(16)
    # Survival terminal on the thief's final step (unless it's a caught answer);
    # the blind cop needs it or it waits out its budget (kit turnloop.py:183,303).
    win_claim = (
        {"type": "survival"} if (role == "thief" and step == max_steps and not caught) else None
    )
    # The cop claims its own cell EVERY turn — the reference peer's own policy
    # (kit turnloop.py:169): the claim just asks "am I standing on you?", the
    # thief's honest answer settles co-location, and there is no claim penalty.
    # Without this our cop could never initiate a capture settlement at all.
    capture_claim = _to_wire_cell(mover.pos) if role == "police" else None
    our_last_claim = list(mover.pos) if capture_claim is not None else None
    turn, record = build_turn(
        record_payload=record_payload,
        nonce=step_nonce,
        sender=role,
        hint=hint_text,
        smell_grid=mover.our_smell_grid(),
        barrier_placed=_to_wire_cell(mover.last_barrier),
        capture_claim=capture_claim,
        claim_response=answer,
        win_claim=win_claim,
    )
    await out_session.send_turn(turn, record)
    return caught, win_claim, our_last_claim
