"""Final audit and nonce-verification helpers for GameRunner."""

import logging

from agent.mcp.client import GameMCPClient
from agent.mcp.crypto import verify_commitment
from agent.mcp.messages import ActionMessage

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


async def final_audit(runner: object, game_id: str, last_step: int) -> tuple[bool, dict]:
    """Collect nonces from both agents and verify all commitments."""
    cop_nonces = await request_nonces(runner, runner.cop_client, game_id, last_step, "cop")
    thief_nonces = await request_nonces(runner, runner.thief_client, game_id, last_step, "thief")

    verified = 0
    failed = 0
    details: dict = {}

    for step_str, cop_rev in runner._cop_reveals.items():
        step = int(step_str)
        h_commit = runner._cop_commits.get(step)
        nonce = (cop_nonces or {}).get(str(step))
        if not h_commit or not nonce:
            failed += 1
            details[f"cop_step_{step}"] = "missing_commit_or_nonce"
            continue
        ok = verify_commitment(
            h_commit=h_commit,
            game_id=game_id,
            step=step,
            role="cop",
            state_hash=cop_rev.get("state_hash", ""),
            move=cop_rev.get("move", ""),
            hint=cop_rev.get("hint", ""),
            intent=cop_rev.get("intent", ""),
            nonce=nonce,
        )
        if ok:
            verified += 1
            details[f"cop_step_{step}"] = "ok"
        else:
            failed += 1
            details[f"cop_step_{step}"] = "commitment_mismatch"
            logger.warning(f"[GameRunner] Cop commitment mismatch at step {step}")

    for step_str, thief_rev in runner._thief_reveals.items():
        step = int(step_str)
        h_commit = runner._thief_commits.get(step)
        nonce = (thief_nonces or {}).get(str(step))
        if not h_commit or not nonce:
            failed += 1
            details[f"thief_step_{step}"] = "missing_commit_or_nonce"
            continue
        ok = verify_commitment(
            h_commit=h_commit,
            game_id=game_id,
            step=step,
            role="thief",
            state_hash=thief_rev.get("state_hash", ""),
            move=thief_rev.get("move", ""),
            hint=thief_rev.get("hint", ""),
            intent=thief_rev.get("intent", ""),
            nonce=nonce,
        )
        if ok:
            verified += 1
            details[f"thief_step_{step}"] = "ok"
        else:
            failed += 1
            details[f"thief_step_{step}"] = "commitment_mismatch"
            logger.warning(f"[GameRunner] Thief commitment mismatch at step {step}")

    audit_ok = failed == 0
    runner._log_event(
        "final_audit",
        "initiator",
        "final_audit",
        {"verified": verified, "failed": failed, "audit_ok": audit_ok},
    )
    logger.info(f"[GameRunner] Final audit: {verified} verified, {failed} failed")
    return audit_ok, details


async def request_nonces(
    runner: object,
    client: GameMCPClient,
    game_id: str,
    last_step: int,
    role: str,
) -> dict | None:
    """Send FINAL_AUDIT request and return nonces dict."""
    msg = ActionMessage(
        game_id=game_id,
        step=last_step,
        role="initiator",
        config_sha256=runner.config_sha256,
        timestamp=_now_iso(),
        phase="final_audit",
        nonces={},
    )
    try:
        resp = await client.action(game_id, msg)
        nonces = resp.get("nonces", {})
        runner._log_event("nonces_received", role, "final_audit", {"count": len(nonces)})
        return nonces
    except Exception as e:
        logger.error(f"[GameRunner] Nonce request to {role} failed: {e}", exc_info=True)
        return None
