"""Low-level helpers for the peer turn loop."""

from __future__ import annotations

import asyncio
import logging
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


def _commit_action_description(runtime: PeerRuntime, step: int, h_commit: str) -> str:
    """Build a natural-language description of the COMMIT action for the adapter LLM."""
    msg_dict = ActionMessage(
        game_id=runtime.game_id,
        step=step,
        role=runtime.role,
        config_sha256=runtime.config_sha256,
        timestamp=_now(),
        phase="commit",
        h_commit=h_commit,
    ).to_dict()
    canonical = canonical_json(msg_dict)
    signature = sign_message(msg_dict, runtime.secret)
    return (
        f"Send a COMMIT phase message to the opponent for game '{runtime.game_id}', "
        f"step {step}, role '{runtime.role}'. "
        f"Our commitment hash (h_commit) is '{h_commit}'. "
        f"Pre-computed values if their protocol needs them: "
        f"canonical_message_json={canonical!r}, hmac_signature='{signature}', "
        f"config_sha256='{runtime.config_sha256}'. "
        f"Map these to whatever parameters their COMMIT/action tool expects and call it."
    )


def _reveal_action_description(runtime: PeerRuntime, step: int, payload: dict) -> str:
    """Build a natural-language description of the REVEAL action for the adapter LLM."""
    msg_dict = ActionMessage(
        game_id=runtime.game_id,
        step=step,
        role=runtime.role,
        config_sha256=runtime.config_sha256,
        timestamp=_now(),
        phase="reveal",
        move=payload["move"],
        hint=payload["hint"],
        intent=payload["intent"],
        state_hash=payload["state_hash"],
    ).to_dict()
    canonical = canonical_json(msg_dict)
    signature = sign_message(msg_dict, runtime.secret)
    return (
        f"Send a REVEAL phase message to the opponent for game '{runtime.game_id}', "
        f"step {step}, role '{runtime.role}'. "
        f"Our move is '{payload['move']}', hint='{payload['hint']}', "
        f"intent='{payload['intent']}', state_hash='{payload['state_hash']}'. "
        f"Pre-computed values if their protocol needs them: "
        f"canonical_message_json={canonical!r}, hmac_signature='{signature}', "
        f"config_sha256='{runtime.config_sha256}'. "
        f"Map these to whatever parameters their REVEAL/action tool expects and call it."
    )


async def send_commit(runtime: PeerRuntime, step: int, h_commit: str) -> dict | None:
    """Send our COMMIT to opponent — via LLM protocol adapter if available, else direct."""
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
        known = {
            "game_id": runtime.game_id,
            "message_json": canonical_json(msg_dict),
            "signature": sign_message(msg_dict, runtime.secret),
        }
        try:
            return await asyncio.wait_for(
                adapter.execute(
                    _commit_action_description(runtime, step, h_commit), known_values=known
                ),
                timeout=adapter_timeout,
            )
        except TimeoutError:
            logger.warning(
                f"[PeerTurn] Adapter COMMIT timed out at step {step} ({adapter_timeout}s)"
                " — disabling adapter"
            )
            runtime.protocol_adapter = None
        except Exception as exc:
            logger.warning(
                f"[PeerTurn] Adapter COMMIT failed at step {step}: {exc} — disabling adapter"
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
        return await runtime.opponent_client.action(runtime.game_id, msg)
    except Exception as exc:
        logger.error(f"[PeerTurn] COMMIT send failed at step {step}: {exc}")
        return None


async def send_reveal(runtime: PeerRuntime, step: int, reveal_payload: dict) -> dict | None:
    """Send our REVEAL — via LLM protocol adapter if available, else direct."""
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
        known = {
            "game_id": runtime.game_id,
            "message_json": canonical_json(msg_dict),
            "signature": sign_message(msg_dict, runtime.secret),
        }
        try:
            return await asyncio.wait_for(
                adapter.execute(
                    _reveal_action_description(runtime, step, reveal_payload), known_values=known
                ),
                timeout=adapter_timeout,
            )
        except TimeoutError:
            logger.warning(
                f"[PeerTurn] Adapter REVEAL timed out at step {step} ({adapter_timeout}s)"
                " — disabling adapter"
            )
            runtime.protocol_adapter = None
        except Exception as exc:
            logger.warning(
                f"[PeerTurn] Adapter REVEAL failed at step {step}: {exc} — disabling adapter"
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
        return await runtime.opponent_client.action(runtime.game_id, msg)
    except Exception as exc:
        logger.error(f"[PeerTurn] REVEAL send failed at step {step}: {exc}")
        return None


async def select_move(runtime: PeerRuntime, board_state: dict) -> str:
    """Choose a move: RL policy → deterministic heuristic.

    LLM movement is forbidden unless both peers opted in via Step-0
    allow_llm_movement=true. Use LLM only for hints and profiling.
    """
    obs = runtime._build_observation(board_state)

    # RL policy path
    try:
        move = runtime._select_move_rl(obs)
        if move:
            return move
    except Exception as exc:
        logger.warning(f"[PeerTurn] RL move selection failed: {exc}")

    # Deterministic heuristic fallback (always available, no LLM)
    from agent.board import Board

    moves = Board.from_dict(board_state).get_legal_moves(runtime.role)
    logger.debug(f"[PeerTurn] heuristic fallback move: {moves[0] if moves else 'STAY'}")
    return moves[0] if moves else "STAY"


def build_board_state(runtime: PeerRuntime) -> dict:
    """Snapshot current board as a plain dict for hashing."""
    b = runtime.board
    return {"cop_position": b.cop_position, "thief_position": b.thief_position, "turn": b.turn}


def get_watchdog_timeout() -> float:
    """Load watchdog timeout from shared config, defaulting to 60s."""
    try:
        from agent.config.shared_config import load_shared_config

        cfg = load_shared_config()
        return float(cfg.get("network_and_league", {}).get("watchdog_timeout_sec", 60))
    except Exception:
        return 60.0
