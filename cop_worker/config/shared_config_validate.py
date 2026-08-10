"""Constitution validation rules for the shared game config."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Ordered list of candidates tried when no explicit path is given.
_SEARCH_PATHS = [
    Path("cop/config.toml"),
    Path("thief/config.toml"),
]

# Mandatory top-level game sections
_REQUIRED_SECTIONS = frozenset(
    [
        "board_and_agents",
        "movement_and_barriers",
        "scoring",
        "pheromones",
        "network_and_league",
    ]
)

# Fixed values mandated by Appendix F — any deviation is a compliance failure
_FIXED_VALUES = {
    ("pheromones", "pheromone_center_intensity"): 0.9,
    ("pheromones", "pheromone_decay"): 0.10,
    ("pheromones", "pheromone_grid_size"): 5,
    ("scoring", "technical_loss"): 0,
    ("scoring", "capture_cop"): 20,
    ("scoring", "capture_thief"): 5,
    ("scoring", "survival_cop"): 5,
    ("scoring", "survival_thief"): 10,
    ("scoring", "tie_score"): 2,
    ("scoring", "diversity_reward"): 10,
}

# Minimum values that must not go below the spec floor
_MIN_VALUES = {
    ("board_and_agents", "grid_size"): 7,
    ("movement_and_barriers", "max_barriers"): 14,
    ("movement_and_barriers", "max_moves"): 35,
    ("movement_and_barriers", "survival_threshold"): 35,
}


def _validate(cfg: dict) -> None:
    """Raise ValueError on any Appendix-F compliance violation."""
    for section in _REQUIRED_SECTIONS:
        if section not in cfg:
            raise ValueError(f"Shared config missing required section: [{section}]")

    for (section, key), expected in _FIXED_VALUES.items():
        actual = cfg.get(section, {}).get(key)
        if actual != expected:
            raise ValueError(
                f"Fixed value mismatch: [{section}].{key} must be {expected!r}, got {actual!r}"
            )

    for (section, key), minimum in _MIN_VALUES.items():
        actual = cfg.get(section, {}).get(key)
        if actual is None:
            raise ValueError(f"Mandatory key missing from shared config: [{section}].{key}")
        if actual < minimum:
            raise ValueError(
                f"Minimum value violated: [{section}].{key} must be >= {minimum}, got {actual}"
            )

    if "reports" in cfg:
        raise ValueError(
            "[reports] must be in the private section of config.toml, not inside [game.*]"
        )
