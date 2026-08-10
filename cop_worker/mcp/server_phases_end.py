"""Per-phase inbound action handling (audit, agreement, end, abort); SM advances
before the callback and rolls back if the callback fails."""

from __future__ import annotations

from cop_worker.mcp.coordinator import ProtocolCoordinator
from cop_worker.mcp.log import GameLog
from cop_worker.mcp.messages import ActionMessage
from cop_worker.mcp.protocol import ProtocolState
from cop_worker.mcp.server_common import _GAME_END_VALID_STATES, _err, _invoke_callback


def _phase_final_audit(
    coord: ProtocolCoordinator,
    game_log: GameLog,
    handler_callbacks: dict,
    game_id: str,
    gamelet: int,
    role: str,
    msg: ActionMessage,
    base: dict,
) -> dict:
    ok, err, prev_state = coord.check_final_audit_guard(game_id, gamelet, role)
    if not ok:
        return _err(
            game_log,
            "action:final_audit",
            msg.role,
            "final_audit",
            f"Protocol violation: {err}",
            base,
        )
    game_log.append(
        "final_audit",
        msg.role,
        "final_audit",
        "ok",
        {"step": msg.step, "nonce_count": len(msg.nonces) if msg.nonces else 0},
    )
    result = _invoke_callback(handler_callbacks, game_id, msg)
    return result


def _phase_result_agreement(
    coord: ProtocolCoordinator,
    game_log: GameLog,
    handler_callbacks: dict,
    game_id: str,
    gamelet: int,
    role: str,
    msg: ActionMessage,
    base: dict,
) -> dict:
    current_state = coord.get_state(game_id, gamelet, role)
    if current_state != ProtocolState.RESULT_AGREEMENT:
        return _err(
            game_log,
            "action:result_agreement",
            msg.role,
            "result_agreement",
            f"Protocol violation: result_agreement in state {current_state}",
            base,
        )
    result = _invoke_callback(handler_callbacks, game_id, msg)
    if result.get("ok"):
        coord.on_done(game_id, gamelet, role)
    return result


def _phase_audit_summary(
    coord: ProtocolCoordinator,
    game_log: GameLog,
    handler_callbacks: dict,
    game_id: str,
    gamelet: int,
    role: str,
    msg: ActionMessage,
    base: dict,
) -> dict:
    current_state = coord.get_state(game_id, gamelet, role)
    if current_state not in (ProtocolState.AUDITING, ProtocolState.RESULT_AGREEMENT):
        return _err(
            game_log,
            "action:audit_summary",
            msg.role,
            "audit_summary",
            f"Protocol violation: audit_summary in state {current_state}",
            base,
        )
    return _invoke_callback(handler_callbacks, game_id, msg)


def _phase_game_end(
    coord: ProtocolCoordinator,
    game_log: GameLog,
    handler_callbacks: dict,
    game_id: str,
    gamelet: int,
    role: str,
    msg: ActionMessage,
    base: dict,
) -> dict:
    # Fix 7: Coordinator guard for game_end — only accept in active/audit states
    current_state = coord.get_state(game_id, gamelet, role)
    if current_state is not None and current_state not in _GAME_END_VALID_STATES:
        return _err(
            game_log,
            "action:game_end",
            msg.role,
            "game_end",
            f"Protocol violation: game_end received in state {current_state.value}",
            base,
        )
    game_log.append(
        "game_end",
        msg.role,
        "game_end",
        "ok",
        {"step": msg.step, "reason": msg.reason},
    )
    result = _invoke_callback(handler_callbacks, game_id, msg)
    return result


def _phase_abort(
    coord: ProtocolCoordinator,
    game_log: GameLog,
    handler_callbacks: dict,
    game_id: str,
    gamelet: int,
    role: str,
    msg: ActionMessage,
    base: dict,
) -> dict:
    # Fix 7: Route abort through coordinator for proper logging and state tracking
    coord.on_technical_loss(
        game_id,
        gamelet,
        role,
        reason=f"abort received from {msg.role}",
    )
    game_log.append(
        "abort",
        msg.role,
        "abort",
        "ok",
        {"step": msg.step, "reason": getattr(msg, "reason", "")},
    )
    result = _invoke_callback(handler_callbacks, game_id, msg)
    return result
