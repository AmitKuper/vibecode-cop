"""Canonical shared game configuration — load, validate, and hash the [game.*] sections.

Primary source: cop/config.toml or thief/config.toml (single unified config file).
The [game.*] sections are extracted and validated; everything else is private.
"""

import hashlib
import json
import logging
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)

# Ordered list of candidates tried when no explicit path is given.
_SEARCH_PATHS = [
    Path("cop/config.toml"),
    Path("thief/config.toml"),
]

# Mandatory top-level game sections
_REQUIRED_SECTIONS = frozenset([
    "board_and_agents",
    "movement_and_barriers",
    "scoring",
    "pheromones",
    "network_and_league",
])

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


def canonical_json(obj: dict) -> str:
    """Serialize to canonical JSON (sorted keys, no extra whitespace)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def config_sha256(config: dict) -> str:
    """SHA-256 of canonical JSON of the config dict."""
    return hashlib.sha256(canonical_json(config).encode("utf-8")).hexdigest()


def _resolve_path(path: Path | str | None) -> Path:
    """Return the config file path to use, auto-detecting if not specified."""
    if path is not None:
        return Path(path)
    for candidate in _SEARCH_PATHS:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "No config file found. Expected cop/config.toml or thief/config.toml. "
        "Create one from the template in the repository."
    )


def _extract_game_sections(raw: dict, source: Path) -> dict:
    """Extract the [game.*] sub-tables from a parsed TOML dict."""
    game = raw.get("game", {})
    if not game:
        raise ValueError(
            f"No [game.*] sections found in {source}. "
            "Add [game.board_and_agents], [game.scoring], etc."
        )
    return game


def load_shared_config(path: Path | str | None = None) -> dict:
    """Load, validate, and return the shared game parameters.

    Reads the [game.*] sections from the unified TOML config file.

    Args:
        path: explicit path to cop/config.toml or thief/config.toml.
              Auto-detected from the working directory when omitted.

    Returns:
        dict with keys: board_and_agents, world, movement_and_barriers,
        scoring, pheromones, network_and_league, rate_limiter_gatekeeper.

    Raises:
        FileNotFoundError: config file not found.
        ValueError: mandatory sections or fixed values are wrong.
    """
    resolved = _resolve_path(path)

    if resolved.suffix == ".toml":
        with open(resolved, "rb") as fh:
            raw = tomllib.load(fh)
        cfg = _extract_game_sections(raw, resolved)
    else:
        # Legacy JSON path (kept for backward compatibility with old test fixtures)
        with open(resolved, encoding="utf-8") as fh:
            cfg = json.load(fh)

    _validate(cfg)
    logger.info("Loaded shared config from %s: sha256=%s...", resolved, config_sha256(cfg)[:16])
    return cfg


def get_config_sha256(path: Path | str | None = None) -> str:
    """Return SHA-256 of the canonical game config dict."""
    return config_sha256(load_shared_config(path))


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
