"""Game rules enforcement for Cop process."""

from __future__ import annotations

import logging

from agent.board import Board
from agent.rules_outcomes import GameOutcome, check_game_status

# Re-export so all existing `from agent.rules_engine import GameOutcome` imports work.
__all__ = ["GameOutcome", "RulesEngine"]

logger = logging.getLogger(__name__)


class RulesEngine:
    """Enforces game rules: movement legality, capture, win/loss conditions."""

    # Minimum per mandatory parameter table; can be increased by negotiation
    MAX_TURNS = 35
    COP_WIN_SCORE = 1
    THIEF_WIN_SCORE = 1

    # Fixed scent field parameters (mandatory, not negotiable)
    SCENT_CENTER = 0.9
    SCENT_DECAY = 0.10
    SCENT_FIELD_RADIUS = 2  # 5×5 field = Chebyshev radius 2

    def __init__(self, board: Board, max_turns: int = 35):
        """Initialize rules engine for a game.

        Args:
            board: The game board.
            max_turns: Survival threshold (from shared config). Minimum 35.
        """
        self.board = board
        self.max_turns = max(max_turns, self.MAX_TURNS)
        n = board.grid_size
        self._scent_grid: list[list[float]] = [[0.0] * n for _ in range(n)]

    def validate_move(self, role: str, action: str) -> bool:
        """Return True if action is a legal move for role."""
        if action not in Board.DIRECTIONS:
            return False

        position = (
            self.board.cop_position if role == "cop" else self.board.thief_position
        )
        candidate_actions = self.board.get_candidate_actions(position)

        return action in candidate_actions

    def check_game_status(self) -> GameOutcome:
        """Determine if game is won, lost, or ongoing.

        Returns:
            GameOutcome indicating the result.
        """
        return check_game_status(self.board, self.max_turns)

    def update_scent(self) -> None:
        """Decay existing scent and emit new scent at thief's current position.

        Call this after apply_moves() each turn. Produces an accumulated,
        decaying trail — the cop sees WHERE the thief has been, not WHERE
        it is right now as a pixel-perfect coordinate.
        """
        n = self.board.grid_size
        tx, ty = self.board.thief_position

        # 1. Decay all existing scent by one turn
        for y in range(n):
            for x in range(n):
                self._scent_grid[y][x] = round(
                    self._scent_grid[y][x] * (1.0 - self.SCENT_DECAY), 4
                )

        # 2. Emit fresh scent at current thief position (take max to prevent
        #    decaying below the just-emitted intensity within the same turn)
        for y in range(n):
            for x in range(n):
                dist = max(abs(x - tx), abs(y - ty))
                if dist <= self.SCENT_FIELD_RADIUS:
                    emitted = round(self.SCENT_CENTER * (self.SCENT_DECAY ** dist), 4)
                    self._scent_grid[y][x] = max(self._scent_grid[y][x], emitted)

    def get_scent_field(self) -> list[list[float]]:
        """Return a copy of the accumulated scent field for use in game protocol."""
        return [row[:] for row in self._scent_grid]

    def compute_scent_field(self) -> list[list[float]]:
        """Compute the 5×5 scent field on the full board grid.

        The scent is centered on the thief's position. Intensity decays by
        SCENT_DECAY per Chebyshev distance unit; cells outside SCENT_FIELD_RADIUS
        have zero scent. This is the cop's primary sensing mechanism.

        Returns:
            grid_size × grid_size nested list, indexed [row][col] = [y][x].
        """
        tx, ty = self.board.thief_position
        n = self.board.grid_size
        field = [[0.0] * n for _ in range(n)]
        for y in range(n):
            for x in range(n):
                dist = max(abs(x - tx), abs(y - ty))
                if dist <= self.SCENT_FIELD_RADIUS:
                    field[y][x] = round(self.SCENT_CENTER * (self.SCENT_DECAY ** dist), 4)
        return field

    def apply_moves(self, cop_move: str, thief_move: str) -> bool:
        """Apply both players' moves simultaneously to the board.

        Args:
            cop_move: Cop's action
            thief_move: Thief's action

        Returns:
            True if both moves were valid, False otherwise.
        """
        if not self.validate_move("cop", cop_move):
            logger.error(f"Invalid cop move: {cop_move}")  # noqa: G004
            return False

        if not self.validate_move("thief", thief_move):
            logger.error(f"Invalid thief move: {thief_move}")  # noqa: G004
            return False

        # Apply both moves
        self.board.apply_move("cop", cop_move)
        self.board.apply_move("thief", thief_move)

        # Record move in history
        self.board.move_history.append(
            {
                "turn": self.board.turn,
                "cop_move": cop_move,
                "thief_move": thief_move,
                "cop_position": self.board.cop_position.copy(),
                "thief_position": self.board.thief_position.copy(),
            }
        )

        self.board.turn += 1
        self.update_scent()
        return True
