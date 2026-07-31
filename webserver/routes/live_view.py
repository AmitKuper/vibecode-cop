"""Role-filtered live game view endpoints.

Each role only sees its own position — never the opponent's.
This satisfies hidden-information requirement AC4.
"""

from fastapi import HTTPException

# In-process game state registry; populated by the MCP server when games run.
game_registry: dict[str, dict] = {}


async def live_cop_view(game_id: str) -> dict:
    """Return the cop's role-filtered view of the current game state.

    The cop sees its own position and scent field — never thief_position.
    """
    state = game_registry.get(game_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Game {game_id!r} not found")
    return {
        "game_id": game_id,
        "role": "cop",
        "cop_position": state.get("cop_position"),
        "scent_field": state.get("scent_field", []),
        "turn": state.get("turn"),
        "move_history": state.get("move_history", []),
    }


async def live_thief_view(game_id: str) -> dict:
    """Return the thief's role-filtered view of the current game state.

    The thief sees its own position and last revealed cop position — never cop_position.
    """
    state = game_registry.get(game_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Game {game_id!r} not found")
    return {
        "game_id": game_id,
        "role": "thief",
        "thief_position": state.get("thief_position"),
        "last_revealed_cop_pos": state.get("last_revealed_cop_pos"),
        "turn": state.get("turn"),
        "move_history": state.get("move_history", []),
    }
