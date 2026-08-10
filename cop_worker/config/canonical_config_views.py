"""CanonicalConfig constructors and serialization views (mixin)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from cop_worker.config.canonical_config import CanonicalConfig


class CanonicalConfigViewsMixin:
    """Constructors, dict/JSON export, and repr."""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CanonicalConfig:
        """Build from a flat dict of Appendix-F parameter names."""
        return cls(data)

    @classmethod
    def from_shared_config(cls, shared: dict) -> CanonicalConfig:
        """Build from the nested shared config/game.json structure."""
        board = shared.get("board_and_agents", {})
        movement = shared.get("movement_and_barriers", {})
        scoring = shared.get("scoring", {})
        pheromones = shared.get("pheromones", {})
        network = shared.get("network_and_league", {})

        return cls(
            {
                # MINIMUM fields
                "grid_size": board.get("grid_size", 7),
                "max_barriers": movement.get("max_barriers", 14),
                "max_turns": movement.get("max_moves", 35),
                "survival_threshold": movement.get("survival_threshold", 35),
                # FIXED fields — league
                "num_gamelets": network.get("num_gamelets", 6),
                "min_games_to_pass": network.get("min_games_to_pass", 2),
                "max_counted_games": network.get("max_games_per_team", 10),
                "diversity_reward": network.get("diversity_reward", 10),
                # FIXED fields — scoring
                "capture_cop": scoring.get("capture_cop", 20),
                "capture_thief": scoring.get("capture_thief", 5),
                "survival_cop": scoring.get("survival_cop", 5),
                "survival_thief": scoring.get("survival_thief", 10),
                # FIXED fields — scent model
                "scent_center": pheromones.get("pheromone_center_intensity", 0.9),
                "scent_decay": pheromones.get("pheromone_decay", 0.10),
                "scent_field_size": pheromones.get("pheromone_grid_size", 5),
            }
        )

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a copy of all fields."""
        return dict(self._fields)

    def __repr__(self) -> str:
        return f"CanonicalConfig(sha256={self._sha256[:16]}...)"
