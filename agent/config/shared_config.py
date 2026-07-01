"""Canonical shared game configuration — load, validate, and hash config/game.json."""

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path("config/game.json")

# Mandatory top-level sections
_REQUIRED_SECTIONS = frozenset([
    "board_and_agents",
    "movement_and_barriers",
    "scoring",
    "pheromones",
    "network_and_league",
    "rate_limiter_gatekeeper",
])

# Fixed values that must not deviate
_FIXED_VALUES = {
    ("movement_and_barriers", "diagonal_moves"): False,
    ("pheromones", "pheromone_center_intensity"): 0.9,
    ("pheromones", "pheromone_decay"): 0.10,
    ("pheromones", "pheromone_grid_size"): 5,
    ("scoring", "technical_loss"): 0,
}

# Minimum values that must not go below PDF floor
_MIN_VALUES = {
    ("movement_and_barriers", "max_barriers"): 14,
    ("movement_and_barriers", "max_moves"): 35,
    ("movement_and_barriers", "survival_threshold"): 35,
    ("network_and_league", "num_gamelets"): 1,
}


def canonical_json(obj: dict) -> str:
    """Serialize to canonical JSON (sorted keys, no extra whitespace)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def config_sha256(config: dict) -> str:
    """SHA-256 of canonical JSON of the config dict."""
    return hashlib.sha256(canonical_json(config).encode("utf-8")).hexdigest()


def load_shared_config(path: Path | str = _DEFAULT_PATH) -> dict:
    """Load, validate, and return the shared game config.

    Raises:
        FileNotFoundError: if config/game.json is missing.
        ValueError: if mandatory sections/values are wrong.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Shared config not found: {path}. "
            "Create config/game.json with all agreed parameters."
        )
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)

    _validate(cfg)
    logger.info(f"Loaded shared config from {path}: sha256={config_sha256(cfg)[:16]}...")
    return cfg


def get_config_sha256(path: Path | str = _DEFAULT_PATH) -> str:
    """Return SHA-256 of the config file contents (canonical JSON of parsed dict)."""
    cfg = load_shared_config(path)
    return config_sha256(cfg)


def _validate(cfg: dict) -> None:
    """Raise ValueError on any compliance violation."""
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
        if actual is not None and actual < minimum:
            raise ValueError(
                f"Minimum value violated: [{section}].{key} must be >= {minimum}, got {actual}"
            )

    if "reports" in cfg:
        raise ValueError(
            "[reports] section must be in private agent config, not shared config/game.json"
        )
