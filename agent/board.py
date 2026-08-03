"""Game board state management for Cop process."""

from dataclasses import dataclass, field


@dataclass
class Board:
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

    def to_dict(self) -> dict:
        """Serialize board state to dict for hashing and replay."""
        return {
            "turn": self.turn,
            "cop_position": self.cop_position,
            "thief_position": self.thief_position,
            "move_history": self.move_history,
            "grid_size": self.grid_size,
            "barriers": self.barriers,
        }

    @classmethod
    def from_dict(cls, state: dict) -> "Board":
        """Create Board instance from state dict."""
        return cls(
            cop_position=state.get("cop_position", [0, 0]),
            thief_position=state.get("thief_position", [3, 3]),
            turn=state.get("turn", 0),
            move_history=state.get("move_history", []),
            grid_size=state.get("grid_size", 7),
            barriers=state.get("barriers", []),
        )

    def to_state(self) -> dict:
        """Serialize to state dict (alias for to_dict)."""
        return self.to_dict()

    @classmethod
    def from_state(cls, state: dict) -> "Board":
        """Create Board from state dict (alias for from_dict)."""
        return cls.from_dict(state)

    def get_position(self, role: str) -> list[int]:
        """Get position for a role.

        Args:
            role: "cop" or "thief"

        Returns:
            [x, y] position
        """
        if role == "cop":
            return self.cop_position
        elif role == "thief":
            return self.thief_position
        else:
            raise ValueError(f"Invalid role: {role}")

    def get_legal_moves(self, role: str) -> list[str]:
        """Return legal move strings for the given role."""
        position = self.get_position(role)
        return self.get_candidate_actions(position)

    def has_orthogonal_escape(self, role: str) -> bool:
        """Return True if role can move to a different cell orthogonally.

        STAY is excluded: a surrounded thief that can only STAY is trapped.
        """
        x, y = self.get_position(role)
        for action, (dx, dy) in self.DIRECTIONS.items():
            if action == "STAY":
                continue
            if self.is_valid_position(x + dx, y + dy):
                return True
        return False
