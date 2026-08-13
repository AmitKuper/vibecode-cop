"""peersim as THIEF (even windows): thief moves first; concede a correct capture claim.

Per-sender numbering: at round r the cop's newest turn is numbered r-1; its
capture_claim is answered on OUR turn r (claim_response rides the next turn). A
correct claim (its cell equals our position) is answered caught=true with a STAY
so the revealed trail ends exactly on the settled cell. At the step cap we send
the survival win_claim — the blind cop needs it or it waits out its budget.
"""

from __future__ import annotations

import secrets

from cop_worker.protocol.reference_v3 import build_turn
from peer_sim_impl.moves import apply_move, hint_for, thief_move
from peer_sim_impl.scent import PreDecayTrail


def _absorb_cop_turn(cop: dict, pos: list[int], blocked: set) -> dict | None:
    """Track the cop's barrier; prepare the claim answer riding our next turn."""
    barrier = cop.get("barrier_placed")
    if isinstance(barrier, (list, tuple)) and len(barrier) == 2:
        blocked.add((int(barrier[0]), int(barrier[1])))
    claim = cop.get("capture_claim")
    if isinstance(claim, (list, tuple)) and len(claim) == 2:
        return {"claim": list(claim), "caught": [int(claim[0]), int(claim[1])] == list(pos)}
    return None


async def play_thief_window(call, inbox, *, sub_game: int, terms: dict, turn_timeout: float):
    """Play one window as thief; returns (records, result_claim)."""
    board = int(terms["board_size"])
    max_steps = int(terms["max_steps"])
    pos = list(terms["thief_start"])
    trail = PreDecayTrail(board, terms)
    blocked: set[tuple[int, int]] = set()
    records: list[dict] = []
    answer: dict | None = None
    for step in range(1, max_steps + 1):
        if step > 1:
            cop = await inbox.wait_turn("police", step - 1, timeout=turn_timeout)
            answer = _absorb_cop_turn(cop, pos, blocked)
        caught = bool(answer and answer.get("caught"))
        move = "STAY" if caught else thief_move(pos, board, blocked)
        pos = apply_move(pos, move)
        win_claim = {"type": "survival"} if (step == max_steps and not caught) else None
        payload = {
            "step": step,
            "role": "thief",
            "sub_game": sub_game,
            "position": list(pos),
            "move": move,
            "intent": "truth",
        }
        turn, record = build_turn(
            record_payload=payload,
            nonce=secrets.token_hex(16),
            sender="thief",
            hint=hint_for("thief", step),
            smell_grid=trail.full_turn((pos[0], pos[1])),
            claim_response=answer,
            win_claim=win_claim,
        )
        records.append(record)
        await call("receive_turn", {"message": turn})
        if caught:
            print(
                f"[peersim] w{sub_game} conceding capture at step {step} (cell {pos})",
                flush=True,
            )
            return records, "capture"
    return records, "timeout"
