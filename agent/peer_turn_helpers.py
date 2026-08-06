"""Low-level helpers for the peer turn loop."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from agent.mcp.crypto import canonical_json, sign_message
from agent.mcp.messages import ActionMessage

if TYPE_CHECKING:
    from agent.peer_runtime import PeerRuntime

logger = logging.getLogger(__name__)

_MOVE_ALIASES = {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST", "STAY": "STAY"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _bounded_exchange(
    runtime: PeerRuntime,
    phase: str,
    step: int,
    invoke: Callable[[], Awaitable[dict]],
) -> dict:
    """Execute one idempotent peer request under its durable deadline record."""
    orchestrator = getattr(runtime, "orchestrator", None)
    tracker = getattr(orchestrator, "deadline_tracker", None)
    if tracker is None:
        return await invoke()
    try:
        record = tracker.begin(
            idempotency_key=f"{runtime.game_id}:{step}:{phase}",
            game_uid=runtime.game_id,
            gamelet=max(1, runtime._gamelet_number(runtime.game_id)),
            step=step,
            phase=phase,
        )
    except Exception as exc:
        if runtime.counted_mode:
            runtime.declare_technical_loss(
                f"DeadlineTracker persistence failed before {phase} step {step}",
                subsystem="deadline_tracker",
                step=step,
            )
        raise RuntimeError("deadline record could not be persisted") from exc

    while True:
        try:
            remaining = max(0.001, record.expiry_monotonic - time.monotonic())
            response = await asyncio.wait_for(invoke(), timeout=remaining)
            digest = hashlib.sha256(canonical_json(response).encode("utf-8")).hexdigest()
            tracker.complete(record.request_id, response_digest=digest)
            return response
        except Exception as exc:
            try:
                retry = tracker.fail(record.request_id, error=type(exc).__name__)
            except Exception as persistence_exc:
                if runtime.counted_mode:
                    runtime.declare_technical_loss(
                        f"DeadlineTracker persistence failed after {phase} step {step}",
                        subsystem="deadline_tracker",
                        step=step,
                    )
                raise RuntimeError("deadline failure could not be persisted") from persistence_exc
            if not retry:
                if runtime.counted_mode:
                    runtime.declare_technical_loss(
                        f"peer {phase} deadline exhausted at step {step}",
                        subsystem="peer_deadline",
                        step=step,
                    )
                raise
            await asyncio.sleep(min(record.next_retry_delay(), 0.25))


async def _call_adapted_phase(
    runtime: PeerRuntime,
    phase: str,
    msg_dict: dict,
    semantic_fields: dict,
) -> dict:
    """Apply the locked mapping plan and invoke exactly the mapped MCP tool."""
    adapter = runtime.protocol_adapter
    message_json = canonical_json(msg_dict)
    canonical = {
        **msg_dict,
        **semantic_fields,
        "message_json": message_json,
        "signature": sign_message(msg_dict, runtime.secret),
    }
    request = adapter.adapt_request(phase, canonical)
    raw = await asyncio.wait_for(
        runtime.opponent_client._call_tool(request.tool_name, request.params),
        timeout=getattr(runtime, "adapter_timeout_sec", 45.0),
    )
    response = adapter.adapt_response(
        phase,
        raw,
        expected_protected={"game_id": runtime.game_id, "phase": phase},
    )
    return {**raw, **response.extracted}


async def send_commit(runtime: PeerRuntime, step: int, h_commit: str) -> dict | None:
    """Send COMMIT through the locked deterministic plan, or explicit dev fallback."""
    adapter = getattr(runtime, "protocol_adapter", None)
    if adapter is not None:
        adapter_timeout = getattr(runtime, "adapter_timeout_sec", 45.0)
        msg_dict = ActionMessage(
            game_id=runtime.game_id,
            step=step,
            role=runtime.role,
            config_sha256=runtime.config_sha256,
            timestamp=_now(),
            phase="commit",
            h_commit=h_commit,
        ).to_dict()
        try:
            return await _bounded_exchange(
                runtime,
                "commit",
                step,
                lambda: _call_adapted_phase(runtime, "commit", msg_dict, {"commitment": h_commit}),
            )
        except Exception as exc:
            if runtime.counted_mode:
                raise RuntimeError(
                    f"Deterministic COMMIT adapter failed at step {step}: {exc}"
                ) from exc
            logger.warning(
                "[PeerTurn] Adapter COMMIT failed at step %s after %.1fs: %s "
                "— explicit development fallback",
                step,
                adapter_timeout,
                exc,
            )
            runtime.protocol_adapter = None
    msg = ActionMessage(
        game_id=runtime.game_id,
        step=step,
        role=runtime.role,
        config_sha256=runtime.config_sha256,
        timestamp=_now(),
        phase="commit",
        h_commit=h_commit,
    )
    try:
        return await _bounded_exchange(
            runtime, "commit", step, lambda: runtime.opponent_client.action(runtime.game_id, msg)
        )
    except Exception as exc:
        logger.error(f"[PeerTurn] COMMIT send failed at step {step}: {exc}")
        return None


async def send_reveal(runtime: PeerRuntime, step: int, reveal_payload: dict) -> dict | None:
    """Send REVEAL through the locked deterministic plan, or explicit dev fallback."""
    adapter = getattr(runtime, "protocol_adapter", None)
    if adapter is not None:
        adapter_timeout = getattr(runtime, "adapter_timeout_sec", 45.0)
        msg_dict = ActionMessage(
            game_id=runtime.game_id,
            step=step,
            role=runtime.role,
            config_sha256=runtime.config_sha256,
            timestamp=_now(),
            phase="reveal",
            move=reveal_payload["move"],
            hint=reveal_payload["hint"],
            intent=reveal_payload["intent"],
            state_hash=reveal_payload["state_hash"],
        ).to_dict()
        try:
            return await _bounded_exchange(
                runtime,
                "reveal",
                step,
                lambda: _call_adapted_phase(
                    runtime,
                    "reveal",
                    msg_dict,
                    {
                        "move": reveal_payload["move"],
                        "hint": reveal_payload["hint"],
                        "intent": reveal_payload["intent"],
                        "state_hash": reveal_payload["state_hash"],
                    },
                ),
            )
        except Exception as exc:
            if runtime.counted_mode:
                raise RuntimeError(
                    f"Deterministic REVEAL adapter failed at step {step}: {exc}"
                ) from exc
            logger.warning(
                "[PeerTurn] Adapter REVEAL failed at step %s after %.1fs: %s "
                "— explicit development fallback",
                step,
                adapter_timeout,
                exc,
            )
            runtime.protocol_adapter = None
    msg = ActionMessage(
        game_id=runtime.game_id,
        step=step,
        role=runtime.role,
        config_sha256=runtime.config_sha256,
        timestamp=_now(),
        phase="reveal",
        move=reveal_payload["move"],
        hint=reveal_payload["hint"],
        intent=reveal_payload["intent"],
        state_hash=reveal_payload["state_hash"],
    )
    try:
        return await _bounded_exchange(
            runtime, "reveal", step, lambda: runtime.opponent_client.action(runtime.game_id, msg)
        )
    except Exception as exc:
        logger.error(f"[PeerTurn] REVEAL send failed at step {step}: {exc}")
        return None


async def select_move(runtime: PeerRuntime, board_state: dict) -> str:
    """Choose a move: RL policy (local obs) → deterministic heuristic.

    RL selection via orchestrator is done through the orchestrator path in
    peer_turn_loop.py (select_move_heuristic). This fallback uses only
    legal-move enumeration to avoid leaking hidden coordinates via
    _build_observation. LLM movement is forbidden unless both peers opted in
    via Step-0 allow_llm_movement=true.
    """
    from agent.board import Board

    moves = Board.from_dict(board_state).get_legal_moves(runtime.role)
    logger.debug(f"[PeerTurn] heuristic fallback move: {moves[0] if moves else 'STAY'}")
    return moves[0] if moves else "STAY"


def build_board_state(runtime: PeerRuntime) -> dict:
    """Snapshot current board as a plain dict for hashing.

    Includes all state that affects game progression to prevent hidden-state
    leakage. barriers is sorted for determinism.
    """
    b = runtime.board
    from agent.mcp.coordinator import gamelet_from_game_id

    gamelet = gamelet_from_game_id(runtime.game_id) if runtime.game_id else 0
    # private_local_state_commitment — this dict is hashed via create_commitment()
    return {
        "cop_position": b.cop_position,
        "thief_position": b.thief_position,
        "turn": b.turn,
        "barriers": sorted(b.barriers),
        "cop_barriers_remaining": runtime._cop_barriers_remaining,
        "gamelet": gamelet,
        "config_sha256": runtime.config_sha256,
    }


def build_local_observation(
    role: str,
    own_position: tuple,
    barriers: list,
    opponent_scent: list,
    last_hint: str,
    step: int,
    gamelet: int,
    grid_size: int,
    own_barriers_remaining: int,
    belief_engine=None,
) -> dict:
    """Build role-filtered observation. No hidden opponent coordinate.

    Cop sees its own position + thief scent. Thief sees its own position +
    cop scent. Neither sees the opponent's true coordinates.
    """
    obs = {
        "own_position": own_position,
        "own_barriers_remaining": own_barriers_remaining,
        "known_barriers": barriers,
        "opponent_scent": opponent_scent,
        "last_hint": last_hint,
        "step": step,
        "gamelet": gamelet,
        "grid_size": grid_size,
    }
    if belief_engine is not None:
        obs["belief_heatmap"] = belief_engine.belief.prob.tolist()
        obs["belief_entropy"] = float(belief_engine.belief.entropy)
    # NOTE: never include opponent_position, cop_position (for thief), or thief_position (for cop)
    return obs


def get_watchdog_timeout() -> float:
    """Load watchdog timeout from shared config, defaulting to 60s."""
    try:
        from agent.config.shared_config import load_shared_config

        cfg = load_shared_config()
        return float(cfg.get("network_and_league", {}).get("watchdog_timeout_sec", 60))
    except Exception:
        return 60.0
