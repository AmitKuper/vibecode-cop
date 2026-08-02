"""Tool for applying moves to board state."""

import logging

try:
    from crewai.tools import tool
except ImportError:

    def tool(func):
        return func


from agent.board import Board

logger = logging.getLogger(__name__)


@tool
def apply_move(game_state: dict, role: str, move: str) -> dict:
    """Apply a move to the board and return updated state.

    Args:
        game_state: Current board state dict
        role: "cop" or "thief"
        move: Move to apply ("N", "S", "E", "W", or "STAY")

    Returns:
        Updated game state dict
    """
    try:
        # Create board from state
        board = Board.from_state(game_state)

        # Apply move
        board.apply_move(role, move)

        # Return updated state
        updated_state = board.to_state()
        logger.debug(f"Applied move {move} for {role}")
        return updated_state

    except Exception as e:
        logger.error(f"Error applying move {move} for {role}: {e}", exc_info=True)
        # Return unchanged state on error
        return game_state


@tool
def apply_both_moves(game_state: dict, cop_move: str, thief_move: str) -> dict:
    """Apply both players' moves simultaneously to the board.

    Args:
        game_state: Current board state dict
        cop_move: Cop's move ("N", "S", "E", "W", or "STAY")
        thief_move: Thief's move ("N", "S", "E", "W", or "STAY")

    Returns:
        Updated game state dict after both moves applied
    """
    try:
        # Create board from state
        board = Board.from_state(game_state)

        # Apply both moves
        board.apply_move("cop", cop_move)
        board.apply_move("thief", thief_move)

        # Return updated state
        updated_state = board.to_state()
        logger.debug(f"Applied moves: cop={cop_move}, thief={thief_move}")
        return updated_state

    except Exception as e:
        logger.error(
            f"Error applying moves (cop={cop_move}, thief={thief_move}): {e}",
            exc_info=True,
        )
        # Return unchanged state on error
        return game_state


@tool
def get_legal_moves(game_state: dict, role: str) -> list[str]:
    """Get list of legal moves for a role at current board state.

    Args:
        game_state: Current board state dict
        role: "cop" or "thief"

    Returns:
        List of legal move strings
    """
    try:
        board = Board.from_state(game_state)
        legal_moves = board.get_legal_moves(role)
        logger.debug(f"Legal moves for {role}: {legal_moves}")
        return legal_moves

    except Exception as e:
        logger.error(f"Error getting legal moves for {role}: {e}", exc_info=True)
        # Return all possible moves as fallback
        return ["N", "S", "E", "W", "STAY"]


@tool
def check_board_state(game_state: dict) -> dict:
    """Check positions and validity of board state.

    Args:
        game_state: Current board state dict

    Returns:
        Dict with positions and board validity info
    """
    try:
        board = Board.from_state(game_state)
        cop_pos = board.get_position("cop")
        thief_pos = board.get_position("thief")

        # Check if positions are valid (within 7x7 grid)
        def is_valid_pos(pos):
            return 0 <= pos[0] <= 6 and 0 <= pos[1] <= 6

        result = {
            "cop_position": cop_pos,
            "thief_position": thief_pos,
            "cop_valid": is_valid_pos(cop_pos),
            "thief_valid": is_valid_pos(thief_pos),
            "same_position": cop_pos == thief_pos,
            "step": game_state.get("step", 0),
            "turn": game_state.get("turn", 0),
        }

        logger.debug(
            f"Board state: cop={cop_pos}, thief={thief_pos}, same={result['same_position']}"
        )
        return result

    except Exception as e:
        logger.error(f"Error checking board state: {e}", exc_info=True)
        return {
            "cop_position": [0, 0],
            "thief_position": [0, 0],
            "cop_valid": False,
            "thief_valid": False,
            "same_position": True,
            "error": str(e),
        }
