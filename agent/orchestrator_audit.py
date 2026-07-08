"""Audit and game-end phase handlers mixin for GameOrchestrator."""

import asyncio
import json
import logging
import threading
from pathlib import Path

from agent.mcp.messages import ActionMessage

logger = logging.getLogger(__name__)


class AuditMixin:
    """Mixin providing final_audit, game_end handlers, and report generation."""

    # Attributes expected from GameOrchestrator.__init__
    role: str
    games_dir: Path
    config_sha256: str

    def _handle_final_audit(self, game_id: str, message: ActionMessage) -> dict:
        """Handle FINAL_AUDIT phase: return all stored nonces for verification.

        The GameRunner collects nonces from both agents and verifies all
        commitments against revealed moves. Each agent returns its own nonces.
        """
        try:
            logger.info(f"Final audit for {game_id}")
            my_file = self.games_dir / game_id / f"my_commitments_{self.role}.json"
            if not my_file.exists():
                return {
                    "ok": True, "game_id": game_id,
                    "phase": "final_audit", "nonces": {}, "verified": True,
                }
            with open(my_file) as f:
                all_payloads = json.load(f)
            nonces = {step: p["nonce"] for step, p in all_payloads.items()}
            logger.info(f"Returning {len(nonces)} nonces for {game_id} final audit")
            return {
                "ok": True, "game_id": game_id,
                "phase": "final_audit", "nonces": nonces, "verified": True,
            }
        except Exception as e:
            logger.error(f"Error in final audit: {e}", exc_info=True)
            return {"ok": False, "error": str(e)}

    def _handle_game_end(self, game_id: str, message: ActionMessage) -> dict:
        """Handle GAME_END phase: mark game complete and schedule reports.

        Args:
            game_id: Game identifier
            message: ActionMessage with winner in reason field ("cop" or "thief")
        """
        try:
            winner = message.reason or "unknown"
            logger.info(f"Game {game_id} ended. Winner: {winner}")
            game_state = self._load_game_state(game_id)
            game_state["completed"] = True
            game_state["winner"] = winner
            game_state["ended_at"] = message.timestamp
            self._save_game_state(game_id, game_state)
            # Delete the ephemeral MCP skill file for this game
            if hasattr(self, "cleanup_skill"):
                self.cleanup_skill(game_id)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.generate_reports(game_id, game_state))
            except RuntimeError:
                def _run_reports() -> None:
                    asyncio.run(self.generate_reports(game_id, game_state))
                threading.Thread(target=_run_reports, daemon=True).start()
            logger.info(f"Game {game_id} marked complete. Winner: {winner}")
            return {
                "ok": True, "game_id": game_id,
                "phase": "game_end", "winner": winner, "completed": True,
            }
        except Exception as e:
            logger.error(f"Error in game_end phase: {e}", exc_info=True)
            return {"ok": False, "error": str(e)}

    async def generate_reports(self, game_id: str, game_state: dict) -> None:
        """Generate all reports (file + Gmail) at game end."""
        try:
            from agent.reports.bundle import ReportBundleBuilder
            from agent.reports.manager import ReportManager
            from agent.reports.plugin_factory import ReportPluginFactory

            logger.info(f"Generating reports for {game_id}...")
            context = await ReportBundleBuilder(self.games_dir / game_id).build(
                game_id=game_id,
                role=self.role,
                game_state=game_state,
                result={
                    "winner": game_state.get("winner"),
                    "step": game_state.get("step", 0),
                },
                config_hash=self.config_sha256,
                metadata={"group_id": getattr(self, "group_id", "unknown")},
            )
            try:
                import tomllib
                config_path = Path(
                    "cop/config.toml" if self.role == "cop" else "thief/config.toml"
                )
                reports_config = {}
                if config_path.exists():
                    with open(config_path, "rb") as f:
                        reports_config = tomllib.load(f).get("reports", {})
            except Exception as e:
                logger.warning(f"Failed to load reports config: {e}")
                reports_config = {}

            plugins = await ReportPluginFactory.from_config(reports_config)
            if not plugins:
                logger.info(f"No report plugins configured for {game_id}")
                return

            results = await ReportManager(plugins).generate_all(context)
            for plugin_name, result in results.items():
                if result.ok:
                    logger.info(f"Report [{plugin_name}] {result.status}: {result.destination}")
                else:
                    logger.error(
                        f"Report [{plugin_name}] FAILED: {result.error_code} — {result.error}"
                    )
            logger.info(f"Report generation complete for {game_id}")
        except Exception as e:
            logger.error(f"Report generation failed: {e}", exc_info=True)
