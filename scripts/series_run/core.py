"""``run_series`` — the reachable core (PeerRuntime was removed in Phase 1).

The function raises ``NotImplementedError`` unconditionally after validation.
The original body below that raise was retained for reference only; that
unreachable legacy code now lives verbatim (as never-called functions) in
``series_run.legacy_gamelets`` and ``series_run.legacy_exchange``.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


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
    from cop_worker.config.shared_config import load_shared_config  # noqa: F401

    # PeerRuntime removed in restructure — series now driven by LeagueManager.
    # This legacy script is retained for reference only; use league_manager for production.
    raise NotImplementedError(
        "run_series.py: PeerRuntime was removed in Phase 1 restructure. "
        "Use league_manager to drive series."
    )
