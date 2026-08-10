"""Per-phase inbound action handling (commit and reveal).

Transactional contract: the SM is advanced BEFORE the callback runs; if the
callback fails, the SM is rolled back to the pre-call state.
"""

from __future__ import annotations

from cop_worker.mcp.coordinator import ProtocolCoordinator
from cop_worker.mcp.log import GameLog
from cop_worker.mcp.messages import ActionMessage
from cop_worker.mcp.server_common import _err, _invoke_callback


def _phase_commit(
    coord: ProtocolCoordinator,
    game_log: GameLog,
    handler_callbacks: dict,
    game_id: str,
    gamelet: int,
    role: str,
    msg: ActionMessage,
    base: dict,
) -> dict:
    h_commit = msg.h_commit or ""
    ok, err, cached, prev_state = coord.check_and_advance_inbound_commit(
        game_id, gamelet, role, msg.step, h_commit
    )
    if not ok:
        return _err(
            game_log,
            "action:commit",
            msg.role,
            "commit",
            f"Protocol violation: {err}",
            base,
        )
    if cached is not None:
        return cached  # Exact duplicate — return cached response

    game_log.append_commit(msg.role, msg.step, h_commit)

    result = _invoke_callback(handler_callbacks, game_id, msg)
    if result.get("ok"):
        coord.record_commit_response(game_id, gamelet, role, msg.step, h_commit, result)
        # If passive side returned h_commit, advance COMMIT_RECEIVED → BOTH_COMMITTED
        if result.get("h_commit"):
            coord.on_passive_commit_sent(game_id, gamelet, role, msg.step, result["h_commit"])
    else:
        # Callback failed — rollback SM
        if prev_state is not None:
            coord.rollback_inbound_commit(game_id, gamelet, role, prev_state)
    return result


def _phase_reveal(
    coord: ProtocolCoordinator,
    game_log: GameLog,
    handler_callbacks: dict,
    game_id: str,
    gamelet: int,
    role: str,
    msg: ActionMessage,
    base: dict,
) -> dict:
    move = msg.move or ""
    hint = msg.hint
    intent = msg.intent
    state_hash = msg.state_hash
    ok, err, cached, prev_state = coord.check_and_advance_inbound_reveal(
        game_id,
        gamelet,
        role,
        msg.step,
        move,
        hint=hint,
        intent=intent,
        state_hash=state_hash,
    )
    if not ok:
        return _err(
            game_log,
            "action:reveal",
            msg.role,
            "reveal",
            f"Protocol violation: {err}",
            base,
        )
    if cached is not None:
        return cached

    game_log.append_reveal(msg.role, msg.step, msg.move, msg.hint, msg.intent)

    result = _invoke_callback(handler_callbacks, game_id, msg)
    if result.get("ok"):
        coord.record_reveal_response(
            game_id,
            gamelet,
            role,
            msg.step,
            move,
            result,
            hint=hint,
            intent=intent,
            state_hash=state_hash,
        )
        # If passive side returned move, advance REVEAL_RECEIVED → STEP_VERIFIED
        if result.get("move"):
            coord.on_passive_reveal_sent(game_id, gamelet, role, msg.step, result["move"])
    else:
        if prev_state is not None:
            coord.rollback_inbound_reveal(game_id, gamelet, role, prev_state)
    return result
