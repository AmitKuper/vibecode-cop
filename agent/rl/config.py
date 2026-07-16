"""Config dataclass for RL training environment.

All values default to mandatory-table minimums. Override with negotiated values
from the locked shared config before training or inference.
"""

from dataclasses import dataclass, field


@dataclass
class RLGameConfig:
    """Drives both the training environment and live-game model selection."""

    # Board
    grid_size: int = 7                                    # minimum; negotiable upward
    cop_start: list[int] = field(default_factory=lambda: [0, 0])   # negotiated
    thief_start: list[int] = field(default_factory=lambda: [3, 3]) # negotiated
    barriers: list[list[int]] = field(default_factory=list)        # negotiated; []= open grid

    # Termination
    max_steps: int = 35           # minimum; negotiable upward
    survival_threshold: int = 35  # minimum; matches max_steps by default
    max_barriers: int = 14        # minimum barrier quota for cop

    # Scoring (fixed by rules, not negotiable)
    cop_capture_reward: float = 1.0
    thief_survival_reward: float = 1.0
    step_penalty: float = 0.01    # cop loses this per step; thief gains it

    # Barrier placement (cop can place barriers during play)
    cop_barrier_quota: int = 0         # barriers cop may place per game (0 = disabled)

    # Training enhancements (not part of the game rules)
    use_shaped_rewards: bool = False   # add distance-delta bonus to intermediate rewards
    shaped_reward_scale: float = 0.05  # scale factor for distance-based shaping
    random_starts: bool = False        # randomize cop/thief start positions each episode

    @classmethod
    def from_dict(cls, d: dict) -> "RLGameConfig":
        return cls(
            grid_size=d.get("grid_size", 7),
            cop_start=d.get("cop_start", [0, 0]),
            thief_start=d.get("thief_start", [3, 3]),
            barriers=d.get("barriers", []),
            max_steps=d.get("max_steps", 35),
            survival_threshold=d.get("survival_threshold", 35),
            max_barriers=d.get("max_barriers", 14),
        )
