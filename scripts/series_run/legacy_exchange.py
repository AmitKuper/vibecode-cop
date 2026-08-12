"""Unreachable legacy result exchange retained verbatim from run_series.py.

Second half of the original ``run_series`` body below the unconditional
``raise NotImplementedError`` (peer_result / mcp.coordinator were removed in
the Phase 1 restructure). NEVER called — kept for reference only, exactly as
it appeared inline, with the consumed locals promoted to parameters.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from series_run.legacy_stubs import (
    ResultExchangeError,
    exchange_series_result,
    gamelet_from_game_id,
    get_coordinator,
)
from series_run.tokens import _TOKEN_KEYS

logger = logging.getLogger(__name__)


async def _legacy_exchange_and_write(
    *,
    runtime,
    gamelets: list[dict],
    series_id: str,
    started_at: str,
    config_sha256: str,
    n_gamelets: int,
    cop_total: int,
    thief_total: int,
    series_winner: str,
    games_dir: Path,
    mode,
    RuntimeMode,  # noqa: N803 — was the imported class name in the original body
) -> dict:
    """Never called — unreachable original body (result exchange half)."""
    series_result = {
        "series_id": series_id,
        "config_sha256": config_sha256,
        "n_gamelets": n_gamelets,
        "gamelets": gamelets,
        "cop_total": cop_total,
        "thief_total": thief_total,
        "series_winner": series_winner,
        "started_at": started_at,
        "ended_at": datetime.now(UTC).isoformat(),
        "token_totals": {
            key: sum(record["token_totals"][key] for record in gamelets) for key in _TOKEN_KEYS
        },
    }

    if mode in (RuntimeMode.COUNTED, RuntimeMode.WARMUP):
        # peer_result removed in restructure

        # mcp.coordinator removed in restructure

        is_counted = mode == RuntimeMode.COUNTED
        all_audits_ok = all(g.get("audit_ok") for g in gamelets)
        any_audit_ok = any(g.get("audit_ok") for g in gamelets)
        # Skip only if counted mode requires all-pass, or if no gamelet passed at all
        _skip_exchange = not is_counted and not any_audit_ok
        if not all_audits_ok and not _skip_exchange and not is_counted:
            logger.warning(
                "[run_series] Partial audit pass — attempting warmup result exchange "
                "(%d/%d passed)",
                sum(1 for g in gamelets if g.get("audit_ok")),
                len(gamelets),
            )
        elif _skip_exchange:
            logger.warning(
                "[run_series] Skipping result exchange — no gamelets passed audit "
                "(warmup mode, 0/%d passed)",
                len(gamelets),
            )
        else:
            try:
                agreement_artifact = await exchange_series_result(runtime, series_result)
            except ResultExchangeError as exc:
                if is_counted:
                    raise
                logger.warning("[run_series] WARMUP result exchange failed (non-fatal): %s", exc)
                agreement_artifact = None
            if agreement_artifact is not None:
                series_result["result_agreement"] = agreement_artifact
                signed = runtime._signed_series_result
                last_game_id = gamelets[-1]["game_id"]
                remote_sig = agreement_artifact["remote_signature_hex"]
                result_hash = signed.agreement.agreement_hash()
                step0 = runtime._step0_agreements[last_game_id]
                runtime.orchestrator.record_match_in_ledger(
                    opponent_id=runtime._remote_step0[last_game_id].declaration.group_id,
                    match_id=series_id,
                    counted=is_counted,
                    declaration_hash=step0.agreement_hash,
                    result_hash=result_hash,
                    both_result_signatures=[signed.signature_hex, remote_sig],
                )
                try:
                    delivery_id = runtime.orchestrator.send_report_via_gatekeeper(
                        idempotency_key=f"{series_id}_{runtime.role}",
                        game_id=series_id,
                        result_json=json.dumps(series_result, sort_keys=True, default=str),
                    )
                    series_result["report_delivery_id"] = delivery_id
                except Exception as exc:
                    if is_counted:
                        raise
                    logger.warning(
                        "[run_series] WARMUP report delivery skipped (non-fatal): %s", exc
                    )
                get_coordinator().on_done(
                    last_game_id,
                    gamelet_from_game_id(last_game_id, strict=True),
                    runtime.role,
                )

    out_path = games_dir / f"result_{series_id}_series.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(series_result, indent=2), encoding="utf-8")
    logger.info(
        f"[run_series] Done: {series_winner} wins (cop {cop_total} – thief {thief_total}). "
        f"Result: {out_path}"
    )
    return series_result
