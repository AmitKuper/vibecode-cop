"""Reference-v3 game loops for direct protocol interoperability.

Implements bidirectional play against peers that speak only the league kit's
reference-v3 wire protocol (4 tools: negotiate, receive_turn, submit_audit,
receive_control).  The generic commit-reveal loop cannot be used because the
reference-v3 protocol seals moves until audit.

Police drives (negotiate → wait thief turn → receive_turn per step → submit_audit).
Thief responds (handles inbound negotiate; sends receive_turn first each step; thief-first order).
"""
from __future__ import annotations

import asyncio
import logging
import math
import secrets
from collections import deque
from datetime import UTC, datetime

from agent.adaptive.reference_v3 import (
    ReferenceV3Error,
    ReferenceV3Session,
    build_negotiation,
    build_turn,
    default_terms,
    verify_audit,
    verify_negotiation,
)
from agent.board import Board

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 0.08   # seconds between queue polls
_STEP_TIMEOUT = 30.0    # seconds to wait for one turn exchange
_NEG_TIMEOUT = 20.0     # seconds for negotiate handshake


# ---------------------------------------------------------------------------
# Smell-grid utilities
# ---------------------------------------------------------------------------

def _compute_smell_grid(
    position: list[int],
    *,
    board_size: int = 7,
    grid_size: int = 5,
    emit_intensity: float = 0.9,
    min_center: float = 0.5,
) -> dict[str, float]:
    """Return a smell grid centred on `position`.

    The grid_size×grid_size window is clipped to the board boundary.
    """
    cx, cy = int(position[0]), int(position[1])
    half = grid_size // 2
    result: dict[str, float] = {}
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < board_size and 0 <= ny < board_size:
                dist = math.sqrt(dx * dx + dy * dy)
                intensity = max(min_center, emit_intensity * math.exp(-dist))
                result[f"{nx},{ny}"] = round(intensity, 4)
    return result


def _estimate_position_from_smell(
    smell_grid: dict[str, float],
    board_size: int = 7,
) -> list[int] | None:
    """Return the cell with highest intensity as estimated opponent position."""
    if not smell_grid:
        return None
    best_key = max(smell_grid, key=lambda k: smell_grid[k])
    try:
        parts = best_key.split(",")
        return [int(parts[0]), int(parts[1])]
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Simple position update (single-agent, opponent not tracked live)
# ---------------------------------------------------------------------------

_DIR = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0), "STAY": (0, 0),
        "N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}


def _apply_move(pos: list[int], move: str, board_size: int, barriers: list) -> list[int]:
    dx, dy = _DIR.get(move.upper(), (0, 0))
    nx, ny = pos[0] + dx, pos[1] + dy
    if 0 <= nx < board_size and 0 <= ny < board_size and [nx, ny] not in barriers:
        return [nx, ny]
    return list(pos)


def _legal_moves(pos: list[int], board_size: int, barriers: list) -> list[str]:
    legal = []
    for move, (dx, dy) in _DIR.items():
        if len(move) > 4:  # skip long aliases like NORTH if we have N already
            continue
        nx, ny = pos[0] + dx, pos[1] + dy
        if 0 <= nx < board_size and 0 <= ny < board_size and [nx, ny] not in barriers:
            legal.append(move)
    return legal or ["STAY"]


# ---------------------------------------------------------------------------
# Queue helpers
# ---------------------------------------------------------------------------

async def _wait_from(q: deque, timeout_s: float = _STEP_TIMEOUT):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if q:
            return q.popleft()
        await asyncio.sleep(_POLL_INTERVAL)
    return None


async def _wait_for_negotiate(session, sub_game_number: int, timeout_s: float) -> dict | None:
    """Wait for a negotiate message with the correct sub_game_number, discarding stale ones."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if session.agreements:
            msg = session.agreements.popleft()
            msg_n = msg.get("sub_game_number") if isinstance(msg, dict) else None
            if msg_n == sub_game_number:
                return msg
            logger.warning(
                "[RefV3/thief] discarding stale negotiate sub_game_number=%s (expected %d)",
                msg_n, sub_game_number,
            )
        await asyncio.sleep(_POLL_INTERVAL)
    return None


# ---------------------------------------------------------------------------
# Move selection
# ---------------------------------------------------------------------------

def _select_move(
    orchestrator,
    own_pos: list[int],
    opp_pos: list[int] | None,
    barriers: list,
    step: int,
    gamelet: int,
    last_hint: str,
    role: str,
    board_size: int,
    legal: list[str],
    rules_engine=None,
) -> str:
    if orchestrator is None:
        return legal[0] if legal else "STAY"
    try:
        own_pos_t = tuple(own_pos)
        barriers_t = [tuple(b) for b in barriers]
        opp_scent = None
        if role == "cop" and rules_engine is not None:
            opp_scent = rules_engine.get_scent_field()
        return orchestrator.select_trained_move(
            own_position=own_pos_t,
            barriers=barriers_t,
            barriers_remaining=14 if role == "cop" else 0,
            legal_actions=legal,
            step=step,
            gamelet=gamelet,
            last_hint=last_hint,
            opponent_scent=opp_scent,
        )
    except Exception as exc:
        logger.warning("[RefV3] select_trained_move failed at step %d: %s", step, exc)
        try:
            return orchestrator.select_move_heuristic(
                own_position=tuple(own_pos),
                barriers=[tuple(b) for b in barriers],
                barriers_remaining=14 if role == "cop" else 0,
            )
        except Exception:
            return legal[0] if legal else "STAY"


# ---------------------------------------------------------------------------
# Police (cop) game loop — outbound initiator
# ---------------------------------------------------------------------------

async def play_as_police(
    *,
    local_session: ReferenceV3Session,
    outbound_caller,
    sub_game_number: int,
    terms: dict,
    group_id: str,
    group_name: str,
    orchestrator=None,
    game_dir=None,
) -> dict:
    """Drive one sub-game as police (cop). Returns result dict."""
    board_size = int(terms.get("board_size", 7))
    max_steps = int(terms.get("max_steps", 35))
    cop_start = list(terms.get("cop_start", [0, 0]))
    thief_start = list(terms.get("thief_start", [3, 3]))
    gamelet = sub_game_number

    # --- Negotiate ---
    my_nonce = secrets.token_hex(16)
    my_neg = build_negotiation(
        terms=terms,
        nonce=my_nonce,
        group_id=group_id,
        group_name=group_name,
        role="police",
        sub_game_number=sub_game_number,
    )
    logger.info("[RefV3/police] sub_game=%d sending negotiate", sub_game_number)
    try:
        await outbound_caller("negotiate", {"message": my_neg})
    except Exception as exc:
        logger.error("[RefV3/police] negotiate call failed: %s", exc)
        return {"winner": "technical_loss", "abort_reason": f"negotiate failed: {exc}"}

    # Negotiate is one-shot: police calls it on thief, thief's acknowledgment is
    # the tool return value. No callback expected. Proceed directly to game loop.
    logger.info("[RefV3/police] negotiate sent; proceeding to game loop (session_id=%s)", id(local_session))

    # --- Game loop ---
    my_pos = list(cop_start)
    opp_pos = list(thief_start)
    barriers: list[list[int]] = []
    barriers_remaining = int(terms.get("barriers_max", 14))
    last_hint = ""
    local_records: list[dict] = []

    for step in range(1, max_steps + 1):
        # reference-v3 is thief-first: wait for thief's turn before responding
        their_turn_msg = await _wait_for_turn_message(local_session, step, _STEP_TIMEOUT)
        if their_turn_msg is None:
            logger.warning("[RefV3/police] no receive_turn at step %d (timeout)", step)
            # play blind — do not abort, sparring peer may be slow
        else:
            last_hint = str(their_turn_msg.get("hint", ""))
            opp_smell = their_turn_msg.get("smell_grid", {})
            est = _estimate_position_from_smell(opp_smell, board_size)
            if est is not None:
                opp_pos = est

        legal = _legal_moves(my_pos, board_size, barriers)
        move = _select_move(
            orchestrator, my_pos, opp_pos, barriers, step, gamelet,
            last_hint, "cop", board_size, legal,
        )
        norm_move = {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST"}.get(move, move)
        if norm_move not in ("NORTH", "SOUTH", "EAST", "WEST", "STAY"):
            norm_move = "STAY"

        hint_text = f"step {step}"
        if orchestrator is not None:
            try:
                hint_text, _ = orchestrator.generate_strategic_hint(move, step=step, gamelet=gamelet)
            except Exception:
                pass

        smell = _compute_smell_grid(
            my_pos,
            board_size=board_size,
            emit_intensity=float(terms.get("emit_intensity", 0.9)),
            min_center=float(terms.get("min_center_intensity", 0.5)),
        )
        nonce = secrets.token_hex(16)
        record_payload = {
            "step": step,
            "state": f"grid={board_size}x{board_size};self={my_pos}",
            "position": my_pos,
            "move": f"MOVE:{norm_move}",
            "intent": "truth",
            "hint": hint_text,
        }
        wire_turn, private_record = build_turn(
            record_payload=record_payload,
            nonce=nonce,
            sender="police",
            hint=hint_text,
            smell_grid=smell,
        )
        local_records.append(private_record)

        try:
            await outbound_caller("receive_turn", {"message": wire_turn})
        except Exception as exc:
            logger.error("[RefV3/police] receive_turn at step %d failed: %s", step, exc)
            return {"winner": "technical_loss", "abort_reason": f"receive_turn failed at step {step}"}

        # Update own position
        my_pos = _apply_move(my_pos, norm_move, board_size, barriers)

        # Detect capture
        if my_pos == opp_pos:
            logger.info("[RefV3/police] capture at step %d", step)
            result_claim = "capture"
            break
    else:
        result_claim = "survival"

    # --- Audit ---
    logger.info("[RefV3/police] submitting audit claim=%s steps=%d", result_claim, len(local_records))
    try:
        await outbound_caller("submit_audit", {
            "payload": {
                "sender": "police",
                "records": local_records,
                "result_claim": result_claim,
            }
        })
    except Exception as exc:
        logger.warning("[RefV3/police] submit_audit failed: %s", exc)

    # Wait for thief's audit (thief calls our submit_audit)
    their_audit = await _wait_from(local_session.audits, _NEG_TIMEOUT)
    audit_ok = False
    played_snap = dict(local_session.turns.played)
    logger.info("[RefV3/police] audit: played_snap has %d steps, their_audit=%s",
                len(played_snap), "received" if their_audit is not None else "None")
    if their_audit is not None:
        from agent.adaptive.reference_v3 import reference_commit as _ref_commit
        records = their_audit.get("records", [])
        logger.info("[RefV3/police] audit has %d records; played steps=%s",
                    len(records), sorted(played_snap.keys())[:10])
        for idx in range(min(3, len(records))):
            r = records[idx]
            if not isinstance(r, dict):
                logger.info("[RefV3/police] records[%d] not a dict: %s", idx, type(r))
                continue
            pstep = (r.get("payload") or {}).get("step")
            claimed = r.get("commit") or ""
            if isinstance(r.get("payload"), dict) and isinstance(r.get("nonce"), str):
                recomputed = _ref_commit(r["payload"], r["nonce"])
                match = recomputed == claimed
            else:
                recomputed, match = "?", False
            logger.info("[RefV3/police] records[%d]: payload_step=%s claimed=%s... recomputed=%s... match=%s",
                        idx, pstep, claimed[:16], str(recomputed)[:16], match)
            if pstep is not None and pstep in played_snap:
                logger.info("[RefV3/police]   played[%s]=%s...", pstep, played_snap[pstep][:16])
            elif pstep is not None:
                logger.info("[RefV3/police]   step %s NOT in played_snap", pstep)
        # Use the thief's turns tracked by the inbox (step → commit) to verify their audit
        audit_ok, errors = verify_audit(their_audit, played_snap)
        if errors:
            logger.warning("[RefV3/police] their audit errors (first 3): %s", errors[:3])

    winner = "cop" if result_claim == "capture" else "thief"
    return {
        "winner": winner,
        "result_claim": result_claim,
        "final_step": len(local_records),
        "audit_ok": audit_ok,
        "sub_game": sub_game_number,
    }


# ---------------------------------------------------------------------------
# Thief game loop — inbound responder
# ---------------------------------------------------------------------------

async def play_as_thief(
    *,
    local_session: ReferenceV3Session,
    outbound_caller,
    sub_game_number: int,
    terms: dict,
    group_id: str,
    group_name: str,
    orchestrator=None,
    game_dir=None,
) -> dict:
    """Drive one sub-game as thief. Returns result dict."""
    board_size = int(terms.get("board_size", 7))
    max_steps = int(terms.get("max_steps", 35))
    cop_start = list(terms.get("cop_start", [0, 0]))
    thief_start = list(terms.get("thief_start", [3, 3]))
    gamelet = sub_game_number

    # --- Wait for police's negotiate ---
    # Drain stale agreements (wrong sub_game_number) that arrived during the previous sub-game.
    logger.info("[RefV3/thief] sub_game=%d waiting for police negotiate", sub_game_number)
    their_neg = await _wait_for_negotiate(local_session, sub_game_number, _NEG_TIMEOUT)
    if their_neg is None:
        logger.error("[RefV3/thief] police never sent negotiate")
        return {"winner": "technical_loss", "abort_reason": "no police negotiate"}

    my_nonce = secrets.token_hex(16)
    my_neg = build_negotiation(
        terms=terms,
        nonce=my_nonce,
        group_id=group_id,
        group_name=group_name,
        role="thief",
        sub_game_number=sub_game_number,
        opponent_group=their_neg.get("group_id"),
    )
    try:
        verify_negotiation(my_neg, their_neg)
    except ReferenceV3Error as exc:
        logger.error("[RefV3/thief] police negotiate bad: %s", exc)
        return {"winner": "technical_loss", "abort_reason": str(exc)}

    # Call police's negotiate back
    try:
        await outbound_caller("negotiate", {"message": my_neg})
    except Exception as exc:
        logger.error("[RefV3/thief] negotiate back-call failed: %s", exc)
        return {"winner": "technical_loss", "abort_reason": f"negotiate back-call failed: {exc}"}

    logger.info("[RefV3/thief] negotiate complete")

    # --- Game loop ---
    my_pos = list(thief_start)
    opp_pos = list(cop_start)
    barriers: list[list[int]] = []
    last_hint = ""
    local_records: list[dict] = []

    for step in range(1, max_steps + 1):
        # reference-v3 is thief-first: thief moves before police each step
        legal = _legal_moves(my_pos, board_size, barriers)
        move = _select_move(
            orchestrator, my_pos, opp_pos, barriers, step, gamelet,
            last_hint, "thief", board_size, legal,
        )
        norm_move = {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST"}.get(move, move)
        if norm_move not in ("NORTH", "SOUTH", "EAST", "WEST", "STAY"):
            norm_move = "STAY"

        hint_text = f"step {step}"
        if orchestrator is not None:
            try:
                hint_text, _ = orchestrator.generate_strategic_hint(move, step=step, gamelet=gamelet)
            except Exception:
                pass

        smell = _compute_smell_grid(
            my_pos,
            board_size=board_size,
            emit_intensity=float(terms.get("emit_intensity", 0.9)),
            min_center=float(terms.get("min_center_intensity", 0.5)),
        )
        nonce = secrets.token_hex(16)
        record_payload = {
            "step": step,
            "state": f"grid={board_size}x{board_size};self={my_pos}",
            "position": my_pos,
            "move": f"MOVE:{norm_move}",
            "intent": "truth",
            "hint": hint_text,
        }
        wire_turn, private_record = build_turn(
            record_payload=record_payload,
            nonce=nonce,
            sender="thief",
            hint=hint_text,
            smell_grid=smell,
        )
        local_records.append(private_record)

        # Thief sends turn via receive_turn (same tool as police — reference-v3 uses
        # receive_turn for ALL game turns in both directions; receive_control is for
        # out-of-band control signals only).
        try:
            await outbound_caller("receive_turn", {"message": wire_turn})
        except Exception as exc:
            logger.error("[RefV3/thief] receive_turn at step %d failed: %s", step, exc)

        # Update own position
        my_pos = _apply_move(my_pos, norm_move, board_size, barriers)

        # Check survival threshold
        if step >= max_steps:
            logger.info("[RefV3/thief] survival at step %d", step)
            break

        # Wait for police's turn
        their_turn_msg = await _wait_for_turn_message(local_session, step, _STEP_TIMEOUT)
        if their_turn_msg is None:
            logger.warning("[RefV3/thief] no receive_turn from police at step %d (timeout)", step)
        else:
            last_hint = str(their_turn_msg.get("hint", ""))
            opp_smell = their_turn_msg.get("smell_grid", {})
            est = _estimate_position_from_smell(opp_smell, board_size)
            if est is not None:
                opp_pos = est

        # Detect capture (cop reached us)
        if opp_pos == my_pos:
            logger.info("[RefV3/thief] captured at step %d", step)
            break

    # --- Wait for police audit, then send ours ---
    logger.info("[RefV3/thief] waiting for police audit")
    their_audit = await _wait_from(local_session.audits, _NEG_TIMEOUT)
    audit_ok = False
    if their_audit is not None:
        # Verify police's records against what we received
        played = {}
        for msg in getattr(local_session.turns, 'played', {}).items():
            played[msg[0]] = msg[1]
        audit_ok, errors = verify_audit(their_audit, played)
        if errors:
            logger.warning("[RefV3/thief] police audit errors: %s", errors)

    # Send our audit to police
    try:
        await outbound_caller("submit_audit", {
            "payload": {
                "sender": "thief",
                "records": local_records,
                "result_claim": "survival",
            }
        })
    except Exception as exc:
        logger.warning("[RefV3/thief] submit_audit to police failed: %s", exc)

    # Determine winner: if police claimed capture, they win
    police_claimed_capture = (
        their_audit is not None
        and their_audit.get("result_claim") == "capture"
        and audit_ok
    )
    winner = "cop" if police_claimed_capture else "thief"
    return {
        "winner": winner,
        "result_claim": "survival",
        "final_step": len(local_records),
        "audit_ok": audit_ok,
        "sub_game": sub_game_number,
    }


async def _wait_for_turn_message(session, step: int, timeout_s: float) -> dict | None:
    """Wait for a full turn message at `step` from the session's turn_messages buffer."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        # Check turn_messages deque for a message at this step
        for msg in list(session.turn_messages):
            if isinstance(msg, dict) and int(msg.get("step", -1)) == step:
                try:
                    session.turn_messages.remove(msg)
                except ValueError:
                    pass
                return msg
        # Also accept if inbox has already recorded this step
        if step in session.turns.played:
            return {"step": step, "commit": session.turns.played[step]}
        await asyncio.sleep(_POLL_INTERVAL)
    return None


# ---------------------------------------------------------------------------
# Full series orchestration (6 sub-games, alternating roles)
# ---------------------------------------------------------------------------

async def play_reference_v3_series(
    *,
    local_session: ReferenceV3Session,
    outbound_caller,
    starting_role: str,   # "police" or "thief" — our role in sub-game 1
    terms: dict | None = None,
    group_id: str = "vibecode",
    group_name: str = "vibecode",
    orchestrator=None,
    games_dir=None,
) -> dict:
    """Run all 6 sub-games of a reference-v3 series."""
    if terms is None:
        terms = default_terms()
    results = []
    cop_total = 0
    thief_total = 0

    for sub_game in range(1, 7):
        # Roles alternate each sub-game
        is_police = (starting_role == "police") == (sub_game % 2 == 1)
        logger.info(
            "[RefV3] sub_game=%d role=%s",
            sub_game,
            "police" if is_police else "thief",
        )

        # Reset queues between sub-games.
        # Do NOT clear agreements when we are thief: the opponent (police) may have sent
        # negotiate while we were still settling the previous sub-game. Clearing it would
        # cause a 20s timeout and a technical_loss on every even sub-game.
        if is_police:
            local_session.agreements.clear()
        local_session.audits.clear()
        local_session.controls.clear()
        local_session.turn_messages.clear()
        # ReferenceV3Inbox is stateful — reset by reinitialising
        from agent.adaptive.reference_v3 import ReferenceV3Inbox
        local_session.turns = ReferenceV3Inbox(window=4)
        local_session.local_records = []
        local_session._local_records_by_step = {}
        # Set expected sender so late turns from the previous sub-game are filtered out.
        # When we are police, the opponent (thief) sends turns to us; when thief, police does.
        local_session.expected_turn_sender = "thief" if is_police else "police"

        if is_police:
            result = await play_as_police(
                local_session=local_session,
                outbound_caller=outbound_caller,
                sub_game_number=sub_game,
                terms=terms,
                group_id=group_id,
                group_name=group_name,
                orchestrator=orchestrator,
                game_dir=games_dir,
            )
        else:
            result = await play_as_thief(
                local_session=local_session,
                outbound_caller=outbound_caller,
                sub_game_number=sub_game,
                terms=terms,
                group_id=group_id,
                group_name=group_name,
                orchestrator=orchestrator,
                game_dir=games_dir,
            )

        results.append(result)
        if result.get("winner") == "cop":
            cop_total += 20  # capture_cop
        elif result.get("winner") == "thief":
            thief_total += 10  # survival_thief
        # Technical losses count as 0 for both

        logger.info(
            "[RefV3] sub_game=%d done: winner=%s (running cop=%d thief=%d)",
            sub_game,
            result.get("winner"),
            cop_total,
            thief_total,
        )

    series_winner = "cop" if cop_total > thief_total else ("thief" if thief_total > cop_total else "tie")
    return {
        "series_winner": series_winner,
        "cop_total": cop_total,
        "thief_total": thief_total,
        "sub_games": results,
    }
