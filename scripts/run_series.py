#!/usr/bin/env python3
"""Run a six-gamelet P2P series via PeerRuntime (cop drives, thief responds).

The cop PeerRuntime drives each gamelet by calling the thief's MCP directly —
no central coordinator is involved.

Prerequisites:
  1. Start the thief agent:  python -m thief thief/config.toml
  2. Run this script from the cop repo root:

     python scripts/run_series.py --thief-url http://localhost:5001/mcp

Optional arguments:
  --thief-url     Thief's MCP endpoint  (default: http://localhost:5001/mcp)
  --secret        Shared HMAC secret    (default: dev-secret-change-me)
  --games-dir     Directory for output  (default: cop/games)
  --n-gamelets    Number of gamelets    (default: 6)
  --config        Path to config.toml   (default: cop/config.toml or config.toml)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import tomllib
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stubs for deleted modules (PeerRuntime, peer_result, mcp.coordinator were
# removed in Phase 1 restructure).  These sentinel objects keep ruff F821 clean
# on the unreachable legacy code paths below.
# ---------------------------------------------------------------------------


class _RemovedModule:
    """Placeholder for a module that was removed in Phase 1 restructure."""

    def __init__(self, *_a, **_kw) -> None:  # noqa: ANN001
        raise NotImplementedError("module removed in restructure")

    def __call__(self, *_a, **_kw):  # noqa: ANN001
        raise NotImplementedError("module removed in restructure")


PeerRuntime = _RemovedModule
ResultExchangeError = Exception  # satisfies except-clause; never raised by real code here


async def exchange_series_result(*_a, **_kw):  # noqa: ANN001
    """Stub — peer_result.exchange_series_result was removed in restructure."""
    raise NotImplementedError("peer_result removed in restructure")


def get_coordinator(*_a, **_kw):  # noqa: ANN001
    """Stub — mcp.coordinator.get_coordinator was removed in restructure."""
    raise NotImplementedError("mcp.coordinator removed in restructure")


def gamelet_from_game_id(*_a, **_kw):  # noqa: ANN001
    """Stub — mcp.coordinator.gamelet_from_game_id was removed in restructure."""
    raise NotImplementedError("mcp.coordinator removed in restructure")


_TOKEN_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens")


def _validated_token_totals(value: dict | None = None) -> dict[str, int]:
    """Return explicit non-negative LLM token accounting for final JSON."""
    source = value or {}
    totals: dict[str, int] = {}
    for key in _TOKEN_KEYS:
        raw = source.get(key, 0)
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            raise ValueError(f"invalid {key} token total: {raw!r}")
        totals[key] = raw
    if totals["total_tokens"] != totals["prompt_tokens"] + totals["completion_tokens"]:
        raise ValueError("total_tokens must equal prompt_tokens + completion_tokens")
    return totals


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run a P2P series via cop PeerRuntime.")
    p.add_argument("--thief-url", default=os.getenv("THIEF_URL", "http://localhost:5001/mcp"))
    p.add_argument("--secret", default=os.getenv("SHARED_SECRET", ""))
    p.add_argument("--games-dir", default="cop/games")
    p.add_argument(
        "--n-gamelets",
        type=int,
        default=6,
        help="Number of gamelets (must be >= 6 per league rules; default: 6)",
    )
    p.add_argument("--config", default="")
    p.add_argument(
        "--mode",
        choices=["counted", "warmup", "development"],
        default="development",
        help="Runtime mode (default: development)",
    )
    p.add_argument(
        "--counted",
        action="store_true",
        help="Deprecated alias for --mode counted",
    )
    return p.parse_args()


def _load_config(args: argparse.Namespace) -> dict:
    """Load config.toml for secret and games_dir if not set via CLI."""
    config_path_candidates = (
        [args.config]
        if args.config
        else [
            "cop/config.toml",
            "config.toml",
        ]
    )
    for path_str in config_path_candidates:
        path = Path(path_str)
        if path.exists():
            with open(path, "rb") as f:
                return tomllib.load(f)
    return {}


async def run_series(
    thief_url: str,
    secret: str,
    config_sha256: str,
    games_dir: Path,
    n_gamelets: int,
    group_name: str,
    llm_dict: dict | None = None,
    counted_mode: bool = False,
    mode: "RuntimeMode | None" = None,  # noqa: F821
    orchestrator_config: dict | None = None,
) -> dict:
    """Run n_gamelets via cop PeerRuntime (P2P, no central judge).

    Args:
        thief_url: MCP endpoint of the thief agent.
        secret: Shared HMAC secret.
        config_sha256: SHA-256 of the agreed canonical game config.
        games_dir: Directory to write gamelet results.
        n_gamelets: Number of gamelets to play.
        group_name: League group name.
        llm_dict: Optional LLM configuration dict.
        counted_mode: Deprecated. Use mode=RuntimeMode.COUNTED instead.
        mode: Runtime mode. COUNTED enforces production constraints.
    """
    from cop_worker.runtime_mode import RuntimeMode

    # Resolve effective mode — explicit mode= wins; counted_mode=True is the legacy alias
    if mode is None:
        mode = RuntimeMode.COUNTED if counted_mode else RuntimeMode.DEVELOPMENT
    elif counted_mode and mode == RuntimeMode.DEVELOPMENT:
        mode = RuntimeMode.COUNTED  # --counted overrides --mode development

    # Legacy backward-compatible gamelet check (counted_mode=True path)
    if counted_mode and n_gamelets != 6:
        raise ValueError(f"Counted mode requires exactly 6 gamelets, got {n_gamelets}")

    # New COUNTED mode enforcement (only when mode was explicitly set to COUNTED)
    if mode == RuntimeMode.COUNTED and not counted_mode:
        if n_gamelets != 6:
            raise ValueError(f"COUNTED mode requires exactly 6 gamelets, got {n_gamelets}")
        if not secret or secret in ("dev-secret-change-me", "change-me", ""):
            raise ValueError("COUNTED mode rejected: development/placeholder secret")
        try:
            import subprocess

            sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
            ).strip()
        except Exception:
            sha = "unknown"
        if not sha or sha == "unknown":
            raise ValueError("COUNTED mode rejected: git SHA unknown")
    from cop_worker.config.shared_config import load_shared_config

    # PeerRuntime removed in restructure — series now driven by LeagueManager.
    # This legacy script is retained for reference only; use league_manager for production.
    raise NotImplementedError(
        "run_series.py: PeerRuntime was removed in Phase 1 restructure. "
        "Use league_manager to drive series."
    )

    shared_cfg = load_shared_config()  # noqa: E501
    scoring = shared_cfg.get("scoring", {})
    capture_cop = scoring.get("capture_cop", 20)
    capture_thief = scoring.get("capture_thief", 5)
    survival_cop = scoring.get("survival_cop", 5)
    survival_thief = scoring.get("survival_thief", 10)
    tie_score = scoring.get("tie_score", 2)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    series_id = f"series_{ts}_{uuid.uuid4().hex[:8]}"
    started_at = datetime.now(UTC).isoformat()
    logger.info(f"[run_series] Starting series {series_id} ({n_gamelets} gamelets)")

    gamelets: list[dict] = []
    cop_total = 0
    thief_total = 0
    runtime = PeerRuntime(
        role="cop",
        secret=secret,
        config_sha256=config_sha256,
        opponent_url=thief_url,
        games_dir=games_dir,
        group_name=group_name,
        llm_dict=llm_dict,
        my_endpoint=(orchestrator_config or {}).get("my_endpoint", ""),
        counted_mode=mode == RuntimeMode.COUNTED,
        orchestrator_config=orchestrator_config,
    )

    runtime.reset_for_new_series()

    for idx in range(1, n_gamelets + 1):
        gamelet_label = f"g{idx:02d}"
        game_id = f"{series_id}_{gamelet_label}"
        logger.info(f"[run_series] Gamelet {gamelet_label}: {game_id}")

        try:
            result = await runtime.run_game(game_id=game_id)
            winner = result.get("winner", "unknown")
            audit_ok = result.get("audit_ok", False)

            if winner == "TECHNICAL_LOSS" or not audit_ok:
                cop_pts = thief_pts = 0
            elif "cop_score" in result and "thief_score" in result:
                cop_pts = int(result["cop_score"])
                thief_pts = int(result["thief_score"])
            elif winner == "cop":
                cop_pts, thief_pts = capture_cop, capture_thief
            elif winner == "thief":
                cop_pts, thief_pts = survival_cop, survival_thief
            else:
                cop_pts = thief_pts = tie_score

            cop_total += cop_pts
            thief_total += thief_pts
            gamelet_record = {
                "gamelet": gamelet_label,
                "game_id": game_id,
                "winner": winner,
                "audit_ok": audit_ok,
                "cop_pts": cop_pts,
                "thief_pts": thief_pts,
                "final_step": result.get("final_step"),
                "token_totals": _validated_token_totals(result.get("token_totals")),
            }
        except Exception as exc:
            if mode == RuntimeMode.COUNTED:
                raise
            logger.error(f"[run_series] Gamelet {gamelet_label} failed: {exc}", exc_info=True)
            gamelet_record = {
                "gamelet": gamelet_label,
                "game_id": game_id,
                "winner": "error",
                "audit_ok": False,
                "cop_pts": 0,
                "thief_pts": 0,
                "error": str(exc),
                "token_totals": _validated_token_totals(),
            }

        gamelets.append(gamelet_record)
        logger.info(
            f"[run_series] {gamelet_label}: winner={gamelet_record['winner']} "
            f"cop+={gamelet_record['cop_pts']} thief+={gamelet_record['thief_pts']}"
        )

    series_winner = (
        "cop" if cop_total > thief_total else "thief" if thief_total > cop_total else "tie"
    )
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


async def main() -> int:
    from cop_worker.logging_setup import setup_dual_logging

    args = _parse_args()
    setup_dual_logging(prefix="run_series_cop")
    config = _load_config(args)

    secret = (
        args.secret
        or os.environ.get("SHARED_SECRET")
        or (config.get("crypto", {}).get("shared_secret", "dev-secret-change-me"))
    )
    games_dir = Path(args.games_dir)
    thief_url = args.thief_url
    if not thief_url.endswith("/mcp"):
        thief_url = thief_url.rstrip("/") + "/mcp"

    from cop_worker.config.shared_config import config_sha256 as _sha256_fn
    from cop_worker.config.shared_config import load_shared_config

    game_cfg = load_shared_config()
    config_sha256 = _sha256_fn(game_cfg)
    group_name = game_cfg.get("network_and_league", {}).get("group_name", "unknown")

    llm_dict = config.get("llm") or None

    from cop_worker.runtime_mode import RuntimeMode

    mode = RuntimeMode.COUNTED if args.counted else RuntimeMode(args.mode)

    # Build orchestrator config with Gmail sender if configured
    orchestrator_config: dict | None = None
    gmail_cfg = config.get("reports", {}).get("gmail", {})
    if gmail_cfg.get("mode") == "send" or gmail_cfg.get("token_path"):
        try:
            from league_manager.gmail.sender import GmailApiSender

            token_path = gmail_cfg.get("token_path", "secrets/gmail/token.json")
            orchestrator_config = {"gmail_sender": GmailApiSender(token_path)}
            logger.info("[run_series] Gmail sender loaded from %s", token_path)
        except Exception as exc:
            logger.warning("[run_series] Gmail sender not available: %s", exc)

    # Counted series must be exactly 6 gamelets (binding league rule).
    if args.n_gamelets != 6:
        logger.error(
            f"[run_series] --n-gamelets {args.n_gamelets} rejected. "
            "Counted series requires exactly 6 gamelets."
        )
        return 1
    n_gamelets = 6
    result = await run_series(
        thief_url=thief_url,
        secret=secret,
        config_sha256=config_sha256,
        games_dir=games_dir,
        n_gamelets=n_gamelets,
        group_name=group_name,
        llm_dict=llm_dict,
        mode=mode,
        orchestrator_config=orchestrator_config,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
