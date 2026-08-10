"""The closed fourteen-key terms: config derivation, defaults, and surface checks."""

from __future__ import annotations

from cop_worker.protocol.introspector import IntrospectionResult
from cop_worker.protocol.reference_v3.constants import (
    REFERENCE_V3_TOOLS,
    TERMS_KEYS,
    ReferenceV3Error,
)

_FALLBACK_TERMS = {
    "board_size": 7,
    "smell_grid_size": 5,
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "min_center_intensity": 0.5,
    "max_steps": 35,
    "barriers_max": 14,
    "setting": "New York",
    "hint_max_words": 15,
    "axis_origin_corner": "top-left",
    "axis_start_index": 0,
    "thief_start": [3, 3],
    "cop_start": [0, 0],
    "num_games": 6,
}


def terms_from_game(game: dict) -> dict:
    """Map a config/game.json constitution dict to the closed 14-key reference-v3 terms.

    game.json is the single source of truth for every game parameter; deriving the wire
    terms (and thus game_uid) from it guarantees the terms, config_sha256, and physics
    cannot silently drift apart.
    """
    board = game.get("board_and_agents", {})
    world = game.get("world", {})
    movement = game.get("movement_and_barriers", {})
    pher = game.get("pheromones", {})
    network = game.get("network_and_league", {})
    return {
        "board_size": board.get("grid_size", 7),
        "smell_grid_size": pher.get("pheromone_grid_size", 5),
        "decay_per_step": pher.get("pheromone_decay", 0.1),
        "emit_intensity": pher.get("pheromone_center_intensity", 0.9),
        "min_center_intensity": pher.get(
            "pheromone_min_center_intensity", pher.get("min_center_intensity", 0.5)
        ),
        "max_steps": movement.get("max_moves", 35),
        "barriers_max": movement.get("max_barriers", 14),
        "setting": world.get("map_area", "New York"),
        "hint_max_words": world.get("hint_max_words", 15),
        "axis_origin_corner": board.get("axis_origin_corner", "top-left"),
        "axis_start_index": board.get("axis_start_index", 0),
        "thief_start": list(board.get("thief_start", [3, 3])),
        "cop_start": list(board.get("cop_start", [0, 0])),
        "num_games": network.get("num_games", 6),
    }


def _base_terms() -> dict:
    """Terms from the base constitution (config/game.json); fallback if unavailable."""
    try:
        from cop_worker.config_loader import load_game

        return terms_from_game(load_game())
    except Exception:
        return dict(_FALLBACK_TERMS)


def default_terms(config: dict | None = None) -> dict:
    """Return the closed fourteen-field agreement, allowing explicit pairwise overrides.

    Base values are sourced from config/game.json (single source of truth); ``config``
    supplies per-match overrides (e.g. ``{"setting": "Haifa"}`` for the self-test).
    """
    config = dict(config or {})
    terms = _base_terms()
    unknown = set(config) - set(TERMS_KEYS)
    if unknown:
        raise ReferenceV3Error(f"unknown reference-v3 agreement terms: {sorted(unknown)}")
    terms.update(config)
    if set(terms) != set(TERMS_KEYS) or terms["num_games"] != 6:
        raise ReferenceV3Error("reference-v3 terms must be the closed 14-key, six-game agreement")
    return terms


def _object_argument(tool, argument: str) -> bool:
    schema = tool.input_schema if isinstance(tool.input_schema, dict) else {}
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    prop = properties.get(argument)
    return (
        isinstance(properties, dict)
        and set(properties) == {argument}
        and argument in required
        and isinstance(prop, dict)
        and prop.get("type") == "object"
    )


def is_reference_v3_surface(introspection: IntrospectionResult) -> bool:
    """Recognize the exact four-tool reference surface from sanitized MCP schemas.

    Extra advertised tools are tolerated, but the four protected names must each have the exact
    one-object argument (including the ``submit_audit(payload)`` asymmetry).  Semantic agreement
    is established later by the signed negotiation and model lock, never from descriptions.
    """
    for tool_name, argument in REFERENCE_V3_TOOLS.items():
        tool = introspection.get_tool(tool_name)
        if tool is None or not _object_argument(tool, argument):
            return False
    return True
