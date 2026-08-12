"""The cop-side reference-v3 game loop against the sparring thief."""

from __future__ import annotations

import random
import secrets

from sparring_demo.netutil import _poll_deque, _poll_inbox_step


async def _game_loop(
    out_session,  # ReferenceV3Session connected to sparring (outbound)
    in_session,  # ReferenceV3Session served by our server (inbound from sparring)
    n_sub_games: int,
) -> list[dict]:
    """Run n_sub_games of cop-vs-thief reference-v3 sub-games."""
    from cop_worker.protocol.reference_v3 import (
        build_negotiation,
        build_turn,
        default_terms,
        verify_audit,
        verify_negotiation,
    )

    # The sparring kit's default setting is "Haifa"; override to match it for the
    # self-test. (Our production default is "New York" to match our anrbj666 pairing.)
    terms = default_terms({"setting": "Haifa"})
    group_id = "vibecode-demo-cop"
    group_name = "Vibecode Demo Cop"
    board_size = terms["board_size"]
    max_steps = terms["max_steps"]
    results = []

    for sub_game_n in range(1, n_sub_games + 1):
        print(f"\n[demo] === Sub-game {sub_game_n}/{n_sub_games} (we are police) ===")
        nonce = secrets.token_hex(16)
        our_greeting = build_negotiation(
            terms=terms,
            nonce=nonce,
            group_id=group_id,
            group_name=group_name,
            role="police",
            sub_game_number=sub_game_n,
        )
        await out_session.send_negotiation(our_greeting)
        their_greeting = await _poll_deque(in_session.agreements, label="negotiate", timeout=30.0)
        negotiated = verify_negotiation(our_greeting, their_greeting)
        print(f"[demo]   Handshake OK — opponent={negotiated.opponent_group}")

        pos = list(terms.get("cop_start", [0, 0]))
        rng = random.Random(f"demo-{sub_game_n}")
        moves = ["N", "S", "E", "W", "STAY"]

        for step in range(1, max_steps + 1):
            if step % 5 == 1:
                print(f"[demo]   Step {step}/{max_steps}...", flush=True)
            # Reference-v3: THIEF moves first, then POLICE.
            # Wait for sparring thief's commitment before sending ours.
            await _poll_inbox_step(in_session.turns, step, timeout=20.0)

            move = rng.choice(moves)
            # Apply move first so the recorded position reflects where we land.
            # audit_records checks: position[N] - position[N-1] == delta(move[N]),
            # so position must be the post-move cell, not the pre-move cell.
            if move == "N" and pos[1] > 0:
                pos[1] -= 1
            elif move == "S" and pos[1] < board_size - 1:
                pos[1] += 1
            elif move == "E" and pos[0] < board_size - 1:
                pos[0] += 1
            elif move == "W" and pos[0] > 0:
                pos[0] -= 1
            record_payload = {
                "step": step,
                "role": "police",
                "sub_game": sub_game_n,
                "state": f"grid={board_size}x{board_size};self={pos};barriers=[]",
                "position": list(pos),
                "move": move,
                "intent": "truth",
                "hint": f"demo step {step}",
                "verdict": "moved",
            }
            smell_grid = {f"{pos[0]},{pos[1]}": max(0.0, 0.9 - step * 0.02)}
            step_nonce = secrets.token_hex(16)
            turn, record = build_turn(
                record_payload=record_payload,
                nonce=step_nonce,
                sender="police",
                hint=f"demo step {step}",
                smell_grid=smell_grid,
            )
            await out_session.send_turn(turn, record)

        print(f"[demo]   {max_steps} steps done — exchanging audits")
        await out_session.send_audit("police", "timeout")
        their_audit_payload = await _poll_deque(
            in_session.audits, label="submit_audit", timeout=30.0
        )
        ok, errors = verify_audit(their_audit_payload, dict(in_session.turns.played))
        print(f"[demo]   Audit: ok={ok} errors={errors[:3] if errors else []}")

        control_msg = {
            "kind": "done",
            "sender": "police",
            "sub_game_number": sub_game_n,
            "status": "complete",
            "step_budget": float(max_steps),
            "payload": {},
        }
        await out_session.send_control(control_msg)
        import contextlib

        with contextlib.suppress(TimeoutError):
            await _poll_deque(in_session.controls, label="receive_control", timeout=8.0)

        # Reset inbox for next sub-game
        from cop_worker.protocol.reference_v3 import ReferenceV3Inbox

        in_session.turns = ReferenceV3Inbox(window=4)

        results.append({"sub_game": sub_game_n, "steps": max_steps, "audit_ok": ok})
        print(f"[demo]   Sub-game {sub_game_n} complete")

    return results
