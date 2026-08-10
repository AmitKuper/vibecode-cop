"""Game board state management for Cop process."""

from dataclasses import dataclass, field

from cop_worker.board_serde import BoardSerdeMixin


@dataclass
class Board(BoardSerdeMixin):
    """Represents an N×N game board with cop, thief positions, and optional barriers."""

    GRID_SIZE = 7  # kept for backward compat; prefer self.grid_size
    DIRECTIONS = {
        "NORTH": (0, -1),
        "SOUTH": (0, 1),
        "EAST": (1, 0),
        "WEST": (-1, 0),
        "STAY": (0, 0),
    }

    cop_position: list[int]  # [x, y]
    thief_position: list[int]  # [x, y]
    turn: int = 0
    move_history: list[dict] = field(default_factory=list)
    grid_size: int = 7
    # Each barrier is [x, y]; stored as list for JSON round-trip compatibility.
    barriers: list[list[int]] = field(default_factory=list)

    def is_valid_position(self, x: int, y: int) -> bool:
        """Check if position is within grid bounds and not blocked by a barrier."""
        if not (0 <= x < self.grid_size and 0 <= y < self.grid_size):
            return False
        return [x, y] not in self.barriers

    def get_candidate_actions(self, position: list[int]) -> list[str]:
        """Return legal moves from a position (all orthogonal moves that stay in bounds)."""
        x, y = position
        legal = []
        for action, (dx, dy) in self.DIRECTIONS.items():
            nx, ny = x + dx, y + dy
            if self.is_valid_position(nx, ny):
                legal.append(action)
        return legal

    def apply_move(self, role: str, action: str) -> bool:
        """Apply a move to the board.

        Args:
            role: "cop" or "thief"
            action: One of NORTH, SOUTH, EAST, WEST, STAY

        Returns:
            True if move was valid and applied, False otherwise.
        """
        if action not in self.DIRECTIONS:
            return False

        if role == "cop":
            position = self.cop_position
        elif role == "thief":
            position = self.thief_position
        else:
            return False

        dx, dy = self.DIRECTIONS[action]
        nx, ny = position[0] + dx, position[1] + dy

        if not self.is_valid_position(nx, ny):
            return False

        if role == "cop":
            self.cop_position = [nx, ny]
        else:
            self.thief_position = [nx, ny]

        return True

    def is_capture(self) -> bool:
        """Return True if cop occupies the thief's cell, or a placed barrier traps the thief."""
        return self.cop_position == self.thief_position or self.thief_position in self.barriers

    def place_barrier(self, x: int, y: int) -> bool:
        """Place a barrier at (x, y).

        Returns True if the barrier was placed (and if it lands on the thief,
        that counts as capture — the caller should check is_capture() after).
        Returns False if position is out of bounds or already a barrier.
        """
        if not (0 <= x < self.grid_size and 0 <= y < self.grid_size):
            return False
        if [x, y] in self.barriers:
            return False
        self.barriers.append([x, y])
        return True
