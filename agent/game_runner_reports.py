"""Report pipeline execution for GameRunner (R5/R6/R7)."""

import logging
from pathlib import Path

from agent.game_runner_output import write_json

logger = logging.getLogger(__name__)


async def generate_reports(runner: object, game_id: str, game_state: dict) -> None:
    """Run the report plugin pipeline (R5/R6/R7)."""
    try:
        import tomllib

        from agent.reports.bundle import ReportBundleBuilder
        from agent.reports.manager import ReportManager
        from agent.reports.plugin_factory import ReportPluginFactory

        context = await ReportBundleBuilder(runner._game_dir).build(
            game_id=game_id, role="initiator", game_state=game_state,
            result={"winner": game_state.get("winner"), "step": game_state.get("final_step", 0)},
            config_hash=runner.config_sha256, metadata={},
        )
        reports_config: dict = {}
        try:
            config_path = Path("cop/config.toml")
            if config_path.exists():
                with open(config_path, "rb") as f:
                    reports_config = tomllib.load(f).get("reports", {})
        except Exception:
            pass
        plugins = await ReportPluginFactory.from_config(reports_config)
        if not plugins:
            logger.info(f"[GameRunner] No report plugins configured for {game_id}")
            return
        results = await ReportManager(plugins).generate_all(context)
        plugin_results_list = []
        for pname, pr in results.items():
            plugin_results_list.append({
                "plugin": pname, "ok": pr.ok, "status": pr.status,
                "destination": pr.destination, "error": pr.error,
            })
            if pr.ok:
                logger.info(f"[GameRunner] Report [{pname}] {pr.status}: {pr.destination}")
            else:
                logger.error(f"[GameRunner] Report [{pname}] FAILED: {pr.error}")
        write_json(runner._game_dir / "report_plugin_results.json",
                   {"game_id": game_id, "plugins": plugin_results_list})
    except Exception as e:
        logger.error(f"[GameRunner] Report pipeline failed: {e}", exc_info=True)
