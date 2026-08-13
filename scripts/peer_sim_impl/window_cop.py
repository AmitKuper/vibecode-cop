"""peersim as COP (odd windows): absorb the thief's turn, greedy-chase, claim own cell.

Turn order mirrors the reference: the thief (vibecode) moves FIRST every round;
per-sender numbering means our cop turn for round r is also numbered r and is
sent only after the thief's r arrived. Commit-reveal per turn: reference_commit
over {step, role, sub_game, position, move, intent} with a fresh nonce.
"""

from __future__ import annotations

import secrets

from cop_worker.protocol.reference_v3 import build_turn
from peer_sim_impl.moves import apply_move, cop_move, hint_for, scent_argmax
from peer_sim_impl.scent import PreDecayTrail


async def play_cop_window(call, inbox, *, sub_game: int, terms: dict, turn_timeout: float):
    """Play one window as police; returns (records, result_claim)."""
    board = int(terms["board_size"])
    max_steps = int(terms["max_steps"])
    pos = list(terms["cop_start"])
    trail = PreDecayTrail(board, terms)
    records: list[dict] = []
    captured = False
    for step in range(1, max_steps + 1):
        opp = await inbox.wait_turn("thief", step, timeout=turn_timeout)
        claim_response = opp.get("claim_response") or {}
        if claim_response.get("caught") is True:
            print(
                f"[peersim] w{sub_game} thief answered caught=true at step {step}",
                flush=True,
            )
            captured = True
            break
        if (opp.get("win_claim") or {}).get("type") == "survival":
            print(f"[peersim] w{sub_game} thief declared survival at step {step}", flush=True)
            break
        move = cop_move(pos, scent_argmax(opp.get("smell_grid"), board), board)
        pos = apply_move(pos, move)
        payload = {
            "step": step,
            "role": "police",
            "sub_game": sub_game,
            "position": list(pos),
            "move": move,
            "intent": "truth",
        }
        turn, record = build_turn(
            record_payload=payload,
            nonce=secrets.token_hex(16),
            sender="police",
            hint=hint_for("police", step),
            smell_grid=trail.full_turn((pos[0], pos[1])),
            # Kit convention: the cop claims its OWN cell every turn ("am I
            # standing on you?"); the thief's honest answer settles co-location.
            capture_claim=list(pos),
        )
        records.append(record)
        await call("receive_turn", {"message": turn})
    return records, ("capture" if captured else "timeout")
