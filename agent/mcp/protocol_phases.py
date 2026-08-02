"""Phase tracking helpers for the MCP protocol."""

from agent.mcp.protocol import ProtocolPhase


class StepPhaseTracker:
    """Track phases for each step of a game."""

    def __init__(self):
        """Initialize tracker."""
        # step -> {"cop": phase_at_step, "thief": phase_at_step, ...}
        self.step_phases: dict[int, dict] = {}

    def mark_phase(self, step: int, role: str, phase: ProtocolPhase) -> None:
        """Mark which phase a role reached at a step.

        Args:
            step: Step/turn number.
            role: "cop" or "thief".
            phase: Phase reached.
        """
        if step not in self.step_phases:
            self.step_phases[step] = {}
        self.step_phases[step][role] = phase.value

    def both_at_phase(self, step: int, phase: ProtocolPhase) -> bool:
        """Check if both roles have reached a phase at a step.

        Args:
            step: Step number.
            phase: Phase to check.

        Returns:
            True if both "cop" and "thief" are at or past phase.
        """
        if step not in self.step_phases:
            return False

        phases = self.step_phases[step]
        return phases.get("cop") == phase.value and phases.get("thief") == phase.value

    def to_dict(self) -> dict:
        """Serialize for logging."""
        return self.step_phases.copy()
