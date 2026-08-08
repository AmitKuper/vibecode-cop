"""Validate game configuration against Appendix-F fixed/minimum values.

Appendix-F is the sole quantitative authority. All fixed values must match
exactly; all minimum values must be satisfied.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class ScoringConfig(BaseModel):
    capture_cop: int = Field(default=20)
    capture_thief: int = Field(default=5)
    survival_cop: int = Field(default=5)
    survival_thief: int = Field(default=10)
    tie_score: int = Field(default=2)
    technical_loss: int = Field(default=0)


class NetworkLeagueConfig(BaseModel):
    group_name: str = ""
    watchdog_timeout_sec: int = Field(ge=1, default=60)
    token_budget_per_series: int = Field(ge=1, default=200000)


class GameConfig(BaseModel):
    """Validated game configuration.

    Fixed values from Appendix-F are enforced by validators.
    Changing them is a binding rule violation.
    """

    schema_version: str = "1.2"
    grid_size: int = Field(default=7)
    cop_start: tuple[int, int] = (0, 0)
    thief_start: tuple[int, int] = (3, 3)
    max_barriers: int = Field(default=14)
    max_moves: int = Field(default=35)
    survival_threshold: int = Field(default=35)
    hint_max_words: int = Field(default=15)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    network: NetworkLeagueConfig = Field(default_factory=NetworkLeagueConfig)

    @model_validator(mode="after")
    def _enforce_appendix_f(self) -> GameConfig:
        errors: list[str] = []

        # Fixed values (Appendix-F — minimum 7, not a fixed value)
        if self.grid_size < 7:
            errors.append(f"grid_size must be >= 7 (got {self.grid_size})")
        if self.max_barriers != 14:
            errors.append(f"max_barriers must be 14 (got {self.max_barriers})")
        if self.max_moves < 35:
            errors.append(f"max_moves must be >= 35 (got {self.max_moves})")
        if self.survival_threshold < 35:
            errors.append(f"survival_threshold must be >= 35 (got {self.survival_threshold})")
        if self.max_moves < self.survival_threshold:
            errors.append(
                "max_moves must be >= survival_threshold "
                f"(got {self.max_moves} < {self.survival_threshold})"
            )

        # Fixed scoring (Appendix-F)
        s = self.scoring
        expected = {"capture_cop": 20, "capture_thief": 5, "survival_cop": 5, "survival_thief": 10}
        for field_name, expected_val in expected.items():
            actual = getattr(s, field_name)
            if actual != expected_val:
                errors.append(f"scoring.{field_name} must be {expected_val} (got {actual})")

        if errors:
            raise ValueError(
                "Appendix-F constraint violations:\n" + "\n".join(f"  - {e}" for e in errors)
            )
        return self


def game_config_from_dict(raw: dict) -> GameConfig:
    """Build the immutable canonical config from the negotiated shared object."""
    board = raw.get("board_and_agents", {})
    movement = raw.get("movement_and_barriers", {})
    world = raw.get("world", {})
    scoring_raw = raw.get("scoring", {})
    network_raw = raw.get("network_and_league", {})

    return GameConfig(
        schema_version=raw.get("schema_version", "1.2"),
        grid_size=board.get("grid_size", 7),
        cop_start=tuple(board.get("cop_start", [0, 0])),
        thief_start=tuple(board.get("thief_start", [3, 3])),
        max_barriers=movement.get("max_barriers", 14),
        max_moves=movement.get("max_moves", 35),
        survival_threshold=movement.get("survival_threshold", 35),
        hint_max_words=world.get("hint_max_words", 15),
        scoring=ScoringConfig(**scoring_raw),
        network=NetworkLeagueConfig(**network_raw),
    )


def validate_game_config(config_path: Path | str) -> GameConfig:
    """Load and validate config/game.json against Appendix-F constraints.

    Raises ValueError if any binding constraint is violated.
    """
    path = Path(config_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    return game_config_from_dict(raw)
