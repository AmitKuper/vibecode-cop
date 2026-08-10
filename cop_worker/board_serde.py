"""Board serialization, state conversion, and derived queries (mixin)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from cop_worker.board import Board


class BoardSerdeMixin:
    """to/from dict and state round-trips, legal-move and escape queries."""

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
    def from_dict(cls, state: dict) -> Board:
        """Create Board instance from state dict.

        Raises:
            ValueError: if cop_position or thief_position is missing (they must
                not be silently substituted with defaults — doing so would let
                a role-filtered observation reconstruct private opponent state).
        """
        if "cop_position" not in state:
            raise ValueError(
                "Board.from_dict: 'cop_position' is required and must not be silently defaulted. "
                "Do not reconstruct a Board from a role-filtered observation."
            )
        if "thief_position" not in state:
            raise ValueError(
                "Board.from_dict: 'thief_position' is required and must not be silently defaulted. "
                "Do not reconstruct a Board from a role-filtered observation."
            )
        return cls(
            cop_position=state["cop_position"],
            thief_position=state["thief_position"],
            turn=state.get("turn", 0),
            move_history=state.get("move_history", []),
            grid_size=state.get("grid_size", 7),
            barriers=state.get("barriers", []),
        )

    def to_state(self) -> dict:
        """Serialize to state dict (alias for to_dict)."""
        return self.to_dict()

    @classmethod
    def from_state(cls, state: dict) -> Board:
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
