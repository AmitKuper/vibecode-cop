"""PeerRuntime audit and game-end notification helpers."""

from __future__ import annotations

import logging
from pathlib import Path

from agent.mcp.messages import ActionMessage
from agent.peer_audit import load_opponent_commits, run_final_audit

logger = logging.getLogger(__name__)


async def do_final_audit(
    opponent_client,
    game_id: str,
    role: str,
    config_sha256: str,
    my_commits: dict,
    game_dir: Path,
    opponent_role: str,
    last_step: int,
    now_fn,
    *,
    gamelet: int = 0,
) -> tuple[bool, dict]:
    """Send FINAL_AUDIT to opponent, receive their nonces, verify locally.

    On the active (cop) side, advance the ProtocolCoordinator through
    on_audit_begin → on_final_audit_complete → on_done so that the SM
    reaches DONE rather than staying in STEP_VERIFIED indefinitely.
    """
    from agent.mcp.coordinator import get_coordinator

    coord = get_coordinator()

    # Advance SM: STEP_VERIFIED → AUDITING (active side)
    coord.on_audit_begin(game_id, gamelet, role)

    my_nonces = {str(s): p["nonce"] for s, p in my_commits.items()}
    msg = ActionMessage(
        game_id=game_id,
        step=last_step,
        role=role,
        config_sha256=config_sha256,
        timestamp=now_fn(),
        phase="final_audit",
        nonces=my_nonces,
    )
    try:
        resp = await opponent_client.action(game_id, msg)
    except Exception as exc:
        logger.error(f"[PeerRuntime] FINAL_AUDIT call failed: {exc}")
        return False, {"error": str(exc)}

    opp_nonces_raw = resp.get("nonces", {})
    opp_nonces = {int(k): v for k, v in opp_nonces_raw.items()}
    audit_ok, details = run_final_audit(game_dir, game_id, opponent_role, opp_nonces)
    logger.info(f"[PeerRuntime/{role}] Final audit: ok={audit_ok} details={details}")

    if audit_ok:
        # Advance SM: AUDITING → RESULT_AGREEMENT → DONE
        coord.on_final_audit_complete(game_id, gamelet, role)
        coord.on_done(game_id, gamelet, role)
    else:
        coord.on_technical_loss(game_id, gamelet, role, reason="audit_failed")

    return audit_ok, details


async def notify_game_end(
    opponent_client,
    game_id: str,
    role: str,
    config_sha256: str,
    step: int,
    winner: str,
    now_fn,
) -> None:
    """Notify opponent that game has ended."""
    msg = ActionMessage(
        game_id=game_id,
        step=step,
        role=role,
        config_sha256=config_sha256,
        timestamp=now_fn(),
        phase="game_end",
        reason=winner,
    )
    try:
        await opponent_client.action(game_id, msg)
    except Exception as exc:
        logger.warning(f"[PeerRuntime] game_end notification failed: {exc}")


def count_opponent_commits(game_dir: Path) -> int:
    return len(load_opponent_commits(game_dir))
