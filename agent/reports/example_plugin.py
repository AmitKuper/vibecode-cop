"""Example custom report plugin.

This shows how to extend the report plugin system with your own plugins.
"""

import json
import logging

from agent.reports.base import ReportPlugin

logger = logging.getLogger(__name__)


class ExampleCustomPlugin(ReportPlugin):
    """Example: Post-game statistics summary plugin.

    Shows how to create a custom report plugin with unique formatting.
    """

    async def generate(self, game_id: str, game_state: dict, game_dir: str) -> dict:
        """Generate a stats summary report.

        Args:
            game_id: Game identifier
            game_state: Final game state
            game_dir: Path to game memory directory

        Returns:
            Result dict
        """
        try:
            # Extract game data
            winner = game_state.get("winner", "unknown")
            moves = game_state.get("move_history", [])
            cop_pos = game_state.get("cop_position", [0, 0])
            thief_pos = game_state.get("thief_position", [6, 6])

            # Calculate statistics
            cop_moves = [m.get("cop") for m in moves]
            thief_moves = [m.get("thief") for m in moves]

            cop_move_counts = {m: cop_moves.count(m) for m in set(cop_moves)}
            thief_move_counts = {m: thief_moves.count(m) for m in set(thief_moves)}

            # Manhattan distance
            distance = abs(cop_pos[0] - thief_pos[0]) + abs(cop_pos[1] - thief_pos[1])

            stats = {
                "game_id": game_id,
                "winner": winner,
                "total_turns": len(moves),
                "final_distance": distance,
                "cop_position": cop_pos,
                "thief_position": thief_pos,
                "cop_move_frequency": cop_move_counts,
                "thief_move_frequency": thief_move_counts,
                "cop_total_moves": len(cop_moves),
                "thief_total_moves": len(thief_moves),
            }

            # Write stats to file
            from pathlib import Path

            stats_file = Path(game_dir) / game_id / "stats.json"

            with open(stats_file, "w") as f:
                json.dump(stats, f, indent=2)

            logger.info(f"Stats report written to {stats_file}")
            return {
                "ok": True,
                "message": f"Statistics generated: {len(moves)} turns analyzed",
                "destination": str(stats_file),
            }

        except Exception as e:
            logger.error(f"ExampleCustomPlugin failed: {e}", exc_info=True)
            return {
                "ok": False,
                "message": str(e),
                "destination": None,
            }


# To use this plugin:
# Add to short_game.py report manager config:
#     from agent.reports.example_plugin import ExampleCustomPlugin
#     report_manager.add_plugin(ExampleCustomPlugin({"name": "stats_plugin", "enabled": True}))
#
# Or add to plugins_config:
#     {"type": "custom", "enabled": True, "name": "stats_plugin"}  # if auto-loaded
