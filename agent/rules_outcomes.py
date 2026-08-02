"""Game outcome types and outcome-determination logic."""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class GameOutcome(Enum):
    """Result of a game."""

    COP_WIN = "cop_win"
    THIEF_WIN = "thief_win"
    ONGOING = "ongoing"
    TECHNICAL_LOSS = "technical_loss"


def check_game_status(board, max_turns: int) -> GameOutcome:
    """Determine if game is won, lost, or ongoing.

    Args:
        board: The game board (Board instance).
        max_turns: Maximum number of turns before thief wins.

    Returns:
        GameOutcome indicating the result.
    """
    if board.is_capture():
        logger.debug("Game over: Cop captured thief")
        return GameOutcome.COP_WIN

    if board.turn >= max_turns:
        logger.debug("Game over: Max turns reached, thief wins")
        return GameOutcome.THIEF_WIN

    # STAY is always a legal action — trapped detection only applies when the thief
    # has NO legal moves at all (barriers surround all cells AND out-of-bounds).
    # Since STAY is always valid, the thief can never be truly "trapped".
    thief_legal = board.get_legal_moves("thief")
    if not thief_legal:
        logger.debug("Game over: Thief has no legal moves (including STAY), cop wins")
        return GameOutcome.COP_WIN

    return GameOutcome.ONGOING
