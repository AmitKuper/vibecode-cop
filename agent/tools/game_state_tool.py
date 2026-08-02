"""Tool for accessing and manipulating game state."""

import json
import logging
from pathlib import Path

try:
    from crewai.tools import tool
except ImportError:

    def tool(func):
        return func


logger = logging.getLogger(__name__)


@tool
def get_observation(game_id: str, role: str, game_state: dict) -> dict:
    """Generate observation dict from game state for the given role.

    Args:
        game_id: Game identifier
        role: "cop" or "thief"
        game_state: Current board state dict containing:
            - step: current step number
            - cop_position: [x, y]
            - thief_position: [x, y]
            - turn: current turn
            - moves: list of moves so far
            - etc.

    Returns:
        Observation dict specific to the role's perspective
    """
    try:
        if not game_state:
            logger.warning(f"No game state for {game_id}, returning empty observation")
            return {
                "own_position": [0, 0],
                "candidate_actions": ["N", "S", "E", "W", "STAY"],
                "turn": 0,
                "scent_field": [],
                "grid_state": None,
            }

        # Extract positions from game state
        cop_pos = game_state.get("cop_position", [0, 0])
        thief_pos = game_state.get("thief_position", [0, 0])
        turn = game_state.get("turn", 0)

        # Determine own and opponent positions based on role
        own_pos = cop_pos if role == "cop" else thief_pos

        # Generate candidate actions (all legal moves for 7x7 grid)
        candidate_actions = []
        x, y = own_pos
        if x > 0:
            candidate_actions.append("W")  # WEST
        if x < 6:
            candidate_actions.append("E")  # EAST
        if y > 0:
            candidate_actions.append("N")  # NORTH
        if y < 6:
            candidate_actions.append("S")  # SOUTH
        candidate_actions.append("STAY")

        # Get scent data (from game state if available)
        game_state.get("scent", {})

        observation = {
            "own_position": own_pos,
            "candidate_actions": candidate_actions,
            "turn": turn,
            "scent_field": game_state.get("scent_field", []),
            "grid_state": game_state,
            "step": game_state.get("step", 0),
        }

        logger.debug(f"Generated observation for {role} at turn {turn}")
        return observation

    except Exception as e:
        logger.error(f"Error generating observation for {game_id}/{role}: {e}", exc_info=True)
        return {
            "own_position": [0, 0],
            "candidate_actions": ["N", "S", "E", "W", "STAY"],
            "turn": 0,
            "scent_field": [],
            "grid_state": None,
        }


@tool
def load_game_state(game_id: str, memory_dir: Path = Path("agent/memory")) -> dict:
    """Load game state from memory folder.

    Args:
        game_id: Game identifier
        memory_dir: Base memory directory (default: agent/memory)

    Returns:
        Game state dict, or empty dict if not found
    """
    try:
        state_file = memory_dir / game_id / "game_state.json"
        if state_file.exists():
            with open(state_file) as f:
                return json.load(f)
        else:
            logger.warning(f"Game state file not found: {state_file}")
            return {}
    except Exception as e:
        logger.error(f"Error loading game state for {game_id}: {e}", exc_info=True)
        return {}


@tool
def save_game_state(
    game_id: str, game_state: dict, memory_dir: Path = Path("agent/memory")
) -> bool:
    """Save game state to memory folder.

    Args:
        game_id: Game identifier
        game_state: State dict to save
        memory_dir: Base memory directory (default: agent/memory)

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        game_dir = memory_dir / game_id
        game_dir.mkdir(parents=True, exist_ok=True)
        state_file = game_dir / "game_state.json"
        with open(state_file, "w") as f:
            json.dump(game_state, f, indent=2)
        logger.debug(f"Saved game state for {game_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving game state for {game_id}: {e}", exc_info=True)
        return False
