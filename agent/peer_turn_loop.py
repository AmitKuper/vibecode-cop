"""Peer turn loop: each agent drives its own side of the commit-reveal protocol.

No central judge exists. Both agents exchange COMMIT then REVEAL messages
directly via MCP. Each agent verifies the opponent's reveal immediately
after receiving it.

Phase sequence per turn:
  COMMIT_LOCAL → SEND_COMMIT → RECEIVE_OPPONENT_COMMIT →
  REVEAL_LOCAL → SEND_REVEAL → RECEIVE_OPPONENT_REVEAL →
  VERIFY_OPPONENT_REVEAL → APPLY_TURN
"""

import asyncio
import logging
import secrets
from typing import TYPE_CHECKING

from agent.domain.runtime_transition import (
    IllegalJointActionError,
    apply_runtime_transition,
    legal_actions_for_role,
)
from agent.language.hint_policy import generate_hint
from agent.mcp.coordinator import gamelet_from_game_id, get_coordinator
from agent.mcp.crypto import (
    build_private_state_commitment,
    build_public_transition_root,
    canonical_domain_state_root,
    combined_protocol_hash,
    create_commitment,
)
from agent.peer_audit import append_opponent_commit, append_opponent_reveal
from agent.peer_turn_helpers import (
    _MOVE_ALIASES,
    build_board_state,
    get_watchdog_timeout,
    select_move,
    send_commit,
    send_reveal,
)
from agent.rules_engine import GameOutcome, RulesEngine

if TYPE_CHECKING:
    from agent.peer_runtime import PeerRuntime

logger = logging.getLogger(__name__)


def build_transition_evidence(runtime, before, transition, cop_move, thief_move, step, gamelet):
    """Build deterministic public/private roots from the canonical transition."""
    local_map = getattr(runtime, "_local_step0", {})
    remote_map = getattr(runtime, "_remote_step0", {})
    agreement_map = getattr(runtime, "_step0_agreements", {})
    local_step0 = local_map.get(runtime.game_id) if isinstance(local_map, dict) else None
    remote_step0 = remote_map.get(runtime.game_id) if isinstance(remote_map, dict) else None
    agreement = agreement_map.get(runtime.game_id) if isinstance(agreement_map, dict) else None
    local_profile = getattr(getattr(local_step0, "declaration", None), "adapter_mapping_hash", "")
    remote_profile = getattr(getattr(remote_step0, "declaration", None), "adapter_mapping_hash", "")
    profile_hash = combined_protocol_hash(
        local_profile if isinstance(local_profile, str) else "",
        remote_profile if isinstance(remote_profile, str) else "",
    )
    outcome = transition.outcome.value
    public_root = build_public_transition_root(
        game_uid=runtime.game_id,
        gamelet=max(1, gamelet),
        step=step,
        declaration_hash=(
            agreement.agreement_hash
            if agreement is not None and isinstance(agreement.agreement_hash, str)
            else ""
        ),
        config_hash=runtime.config_sha256,
        protocol_hash=profile_hash,
        public_barriers=list(transition.new_state.barriers),
        cop_barriers_quota=transition.new_state.cop_barriers_remaining,
        revealed_cop_move=cop_move,
        revealed_thief_move=thief_move,
        previous_transcript_root=(
            runtime._public_transition_root
            if isinstance(getattr(runtime, "_public_transition_root", ""), str)
            else ""
        ),
        public_outcome=outcome,
    )
    runtime._public_transition_root = public_root
    return {
        "public_transition_root": public_root,
        "state_before_root": canonical_domain_state_root(before, runtime.config_sha256),
        "state_after_root": canonical_domain_state_root(
            transition.new_state, runtime.config_sha256
        ),
        "outcome": outcome,
        "cop_score": transition.cop_score,
        "thief_score": transition.thief_score,
    }


async def run_peer_turn(
    runtime: "PeerRuntime",
    step: int,
    rules: RulesEngine,
) -> tuple[str | None, str | None]:
    """Execute one full commit-reveal turn from this agent's perspective.

    Returns:
        (winner_or_None, abort_reason_or_None) — non-None means game over.
    """
    gamelet = gamelet_from_game_id(runtime.game_id)
    coord = get_coordinator()

    board_state = build_board_state(runtime)

    # Advance SM: READY/STEP_VERIFIED → COMPUTING_MOVE
    coord.begin_step(runtime.game_id, gamelet, runtime.role, step)

    legal_actions = legal_actions_for_role(runtime, rules, runtime.role)
    _has_orch = getattr(runtime, "orchestrator", None) is not None
    if runtime.counted_mode:
        if not _has_orch or not runtime.rl_model_loaded:
            reason = "counted recurrent movement policy is unavailable"
            coord.on_technical_loss(runtime.game_id, gamelet, runtime.role, reason=reason)
            return None, reason
        try:
            _board = runtime.board
            _is_cop = runtime.role == "cop"
            own_pos = tuple(_board.cop_position if _is_cop else _board.thief_position)
            barrier_list = [tuple(b) for b in _board.barriers]
            barriers_remaining = runtime._cop_barriers_remaining if _is_cop else 0
            # Use the rules-engine scent (the training-time authority) for the cop.
            # Thief uses ScentFields which tracks the cop trail (no rules_engine equivalent).
            opp_scent = rules.get_scent_field() if _is_cop else None
            move = runtime.orchestrator.select_trained_move(
                own_position=own_pos,
                barriers=barrier_list,
                barriers_remaining=barriers_remaining,
                legal_actions=legal_actions,
                step=step,
                gamelet=gamelet,
                last_hint=runtime._last_opponent_hint,
                opponent_scent=opp_scent,
            )
        except Exception as policy_error:
            reason = f"counted recurrent policy inference failed: {policy_error}"
            coord.on_technical_loss(runtime.game_id, gamelet, runtime.role, reason=reason)
            return None, reason
    else:
        move = await select_move(runtime, {**board_state, "scent_field": rules.get_scent_field()})
        if _has_orch:
            try:
                _board = runtime.board
                _is_cop = runtime.role == "cop"
                own_pos = tuple(_board.cop_position if _is_cop else _board.thief_position)
                barrier_list = [tuple(b) for b in _board.barriers]
                barriers_remaining = runtime._cop_barriers_remaining if _is_cop else 0
                move = runtime.orchestrator.select_move_heuristic(
                    own_position=own_pos,
                    barriers=barrier_list,
                    barriers_remaining=barriers_remaining,
                )
            except Exception as heuristic_error:
                logger.warning(
                    "[PeerTurn] Development heuristic failed at step %d: %s",
                    step,
                    heuristic_error,
                )

    selected = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}.get(move, move)
    if selected not in legal_actions:
        reason = f"local policy selected illegal action {move!r} at step {step}"
        if runtime.counted_mode:
            coord.on_technical_loss(runtime.game_id, gamelet, runtime.role, reason=reason)
            return None, reason
        logger.warning("[PeerTurn] %s; development fallback=%s", reason, legal_actions[0])
        selected = legal_actions[0]
    move = selected

    # 4B: Use strategic language policy when orchestrator is available
    if getattr(runtime, "orchestrator", None) is not None:
        try:
            hint, intent = runtime.orchestrator.generate_strategic_hint(move, step=step)
        except Exception as _lang_err:
            logger.warning("[PeerTurn] Strategic hint failed at step %d: %s", step, _lang_err)
            from agent.language.hint_policy import generate_hint as _gen_hint

            intent = "truth"
            hint = _gen_hint(move, intent)
    else:
        intent = "truth"
        hint = generate_hint(move, intent)

    nonce = secrets.token_hex(32)
    own_position = tuple(
        runtime.board.cop_position if runtime.role == "cop" else runtime.board.thief_position
    )
    state_hash = build_private_state_commitment(
        own_position=own_position,
        own_barriers_remaining=(runtime._cop_barriers_remaining if runtime.role == "cop" else 0),
        local_nonce=nonce,
        step=step,
        gamelet=max(1, gamelet),
        game_uid=runtime.game_id,
    )
    h_commit, nonce = create_commitment(
        game_id=runtime.game_id,
        step=step,
        role=runtime.role,
        state_hash=state_hash,
        move=move,
        hint=hint,
        intent=intent,
        gamelet=max(1, gamelet),
        nonce=nonce,
    )
    runtime._store_my_commit(
        step,
        {
            "h_commit": h_commit,
            "nonce": nonce,
            "move": move,
            "hint": hint,
            "intent": intent,
            "state_hash": state_hash,
        },
    )
    logger.info(f"[PeerTurn] step={step} committed move={move} h={h_commit[:12]}...")

    opponent_resp = await send_commit(runtime, step, h_commit)
    if not opponent_resp:
        coord.on_technical_loss(
            runtime.game_id, gamelet, runtime.role, reason=f"COMMIT send failed at step {step}"
        )
        return None, f"COMMIT exchange failed at step {step} (send error)"
    opp_h_commit = opponent_resp.get("h_commit")
    if not opp_h_commit:
        coord.on_technical_loss(
            runtime.game_id, gamelet, runtime.role, reason=f"No h_commit in response at step {step}"
        )
        return None, f"Opponent did not return h_commit at step {step}"
    append_opponent_commit(runtime.game_dir, step, opp_h_commit)
    logger.debug(f"[PeerTurn] step={step} stored opponent h_commit={opp_h_commit[:12]}...")

    # Advance SM: COMPUTING_MOVE → COMMIT_SENT → BOTH_COMMITTED
    coord.on_commit_exchange_complete(runtime.game_id, gamelet, runtime.role, step)

    reveal_payload = {
        "move": move,
        "hint": hint,
        "intent": intent,
        "state_hash": state_hash,
    }
    opp_reveal_resp = await send_reveal(runtime, step, reveal_payload)
    if not opp_reveal_resp:
        coord.on_technical_loss(
            runtime.game_id, gamelet, runtime.role, reason=f"REVEAL send failed at step {step}"
        )
        return None, f"REVEAL exchange failed at step {step} (send error)"
    opp_move_short = opp_reveal_resp.get("move")
    if not opp_move_short:
        coord.on_technical_loss(
            runtime.game_id,
            gamelet,
            runtime.role,
            reason=f"No move in REVEAL response at step {step}",
        )
        return None, f"Opponent did not include move in REVEAL at step {step}"

    # Advance SM: BOTH_COMMITTED → REVEAL_SENT → STEP_VERIFIED
    coord.on_reveal_exchange_complete(runtime.game_id, gamelet, runtime.role, step)

    opp_reveal = {
        "move": opp_move_short,
        "hint": opp_reveal_resp.get("hint", ""),
        "intent": opp_reveal_resp.get("intent", "truth"),
        "state_hash": opp_reveal_resp.get("state_hash", ""),
    }
    runtime._last_opponent_hint = opp_reveal["hint"]
    append_opponent_reveal(runtime.game_dir, step, opp_reveal)

    my_move = _MOVE_ALIASES.get(move, move)
    opp_move = _MOVE_ALIASES.get(opp_move_short, opp_move_short)
    cop_move, thief_move = (my_move, opp_move) if runtime.role == "cop" else (opp_move, my_move)

    from agent.domain.runtime_transition import state_from_runtime

    domain_before = state_from_runtime(runtime, rules)
    try:
        transition = apply_runtime_transition(runtime, rules, cop_move, thief_move)
    except IllegalJointActionError as exc:
        reason = f"Protocol violation at step {step}: {exc}"
        coord.on_technical_loss(runtime.game_id, gamelet, runtime.role, reason=reason)
        return None, reason
    if transition.barrier_placed:
        logger.info(
            "[PeerTurn] step=%d cop placed barrier at %s", step, transition.barrier_position
        )
    transition_evidence = build_transition_evidence(
        runtime, domain_before, transition, cop_move, thief_move, step, gamelet
    )

    logger.info("[PeerTurn] step=%d canonical transition applied", step)

    # Wire symmetric scent and belief into AgentOrchestrator after each turn
    if getattr(runtime, "orchestrator", None) is not None:
        runtime.orchestrator.synchronize_domain_state(transition.new_state)

    # 5A: Publish SafeLiveView after each turn
    if getattr(runtime, "orchestrator", None) is not None:
        try:
            _board = runtime.board
            _role = runtime.role
            own_pos = tuple(_board.cop_position if _role == "cop" else _board.thief_position)
            barrier_list = [tuple(b) for b in _board.barriers]
            received_hint = opp_reveal.get("hint", "")
            if hasattr(coord, "get_state"):
                _proto = str(coord.get_state(runtime.game_id, gamelet, _role))
            else:
                _proto = "STEP_VERIFIED"
            runtime.orchestrator.publish_live_view(
                own_position=own_pos,
                barriers=barrier_list,
                last_hint=received_hint or "",
                turn=step,
                gamelet=gamelet,
                protocol_state=_proto,
                your_turn=False,
            )
        except Exception as _lv_err:
            logger.debug("[PeerTurn] publish_live_view failed at step %d: %s", step, _lv_err)

    # 3D: Record step evidence in StepJournal
    if getattr(runtime, "orchestrator", None) is not None:
        try:
            runtime.orchestrator.record_step_evidence(
                gamelet=gamelet,
                step=step,
                local_commitment=h_commit,
                local_move=move,
                received_commitment=opp_h_commit,
                received_move=opp_move_short,
                local_nonce=nonce,
                local_hint=hint,
                local_intent=intent,
                local_state_hash=state_hash,
                received_hint=opp_reveal["hint"],
                received_intent=opp_reveal["intent"],
                received_state_hash=opp_reveal["state_hash"],
                protocol_state_before=str(board_state),
                protocol_state_after=str(build_board_state(runtime)),
                **transition_evidence,
            )
        except Exception as _journal_err:
            if getattr(runtime, "counted_mode", False):
                raise RuntimeError(
                    f"StepJournal write failed in counted mode at step {step}"
                ) from _journal_err
            logger.warning("[PeerTurn] StepJournal write failed at step %d: %s", step, _journal_err)

    outcome = transition.outcome
    if outcome == GameOutcome.COP_WIN:
        return "cop", None
    if outcome == GameOutcome.THIEF_WIN:
        return "thief", None
    return None, None


async def run_peer_turn_loop(
    runtime: "PeerRuntime",
    rules: RulesEngine,
    max_turns: int,
) -> tuple[str | None, str | None, int]:
    """Run all turns for this agent's side of the game.

    Returns:
        (winner, abort_reason, final_step)
    """
    winner = abort_reason = None
    final_step = 0
    watchdog_timeout = get_watchdog_timeout()
    try:
        for step in range(1, max_turns + 1):
            try:
                winner, abort_reason = await asyncio.wait_for(
                    run_peer_turn(runtime, step, rules),
                    timeout=watchdog_timeout,
                )
            except TimeoutError:
                abort_reason = f"Watchdog timeout at step {step}"
                logger.error(f"[PeerTurnLoop] {abort_reason}")
                break
            final_step = int(runtime.board.turn)
            # 3B: emit heartbeat after each completed step
            if getattr(runtime, "orchestrator", None) is not None:
                try:
                    runtime.orchestrator.emit_heartbeat(step=step)
                except Exception as _hb_err:
                    if runtime.counted_mode:
                        abort_reason = f"counted heartbeat persistence failed: {_hb_err}"
                        gamelet = gamelet_from_game_id(runtime.game_id)
                        coord = get_coordinator()
                        coord.on_technical_loss(
                            runtime.game_id,
                            gamelet,
                            runtime.role,
                            reason=abort_reason,
                        )
                        break
                    logger.warning("[PeerTurnLoop] Heartbeat emit failed: %s", _hb_err)
            if winner is not None or abort_reason is not None:
                break
    except Exception as exc:
        logger.error(f"[PeerTurnLoop] Unexpected error: {exc}", exc_info=True)
        abort_reason = str(exc)
    if winner is None and abort_reason is None:
        winner = "thief"
    return winner, abort_reason, final_step
