"""Tool for selecting moves using a trained RL policy (if available).

The crewAI StrategyAgent calls this tool with an observation dict.
If no RL model is found the tool raises — the agent must reason about the
move itself from the board description in the task prompt.
"""

import logging
from pathlib import Path

try:
    from crewai.tools import tool
except ImportError:

    def tool(func):  # type: ignore[misc]
        return func


logger = logging.getLogger(__name__)

_rl_policies: dict = {}


def _load_rl_policy(role: str):
    """Load and cache the best available RL policy for a role, or return None."""
    if role in _rl_policies:
        return _rl_policies[role]

    try:
        from agent.rl.policy import RLPolicy

        models_dir = Path("models")
        preferred = (
            ["cop_ppo_league_best.pt", "cop_ppo_best.pt", "cop_ppo.pt"]
            if role == "cop"
            else ["thief_ppo_league_best.pt", "thief_ppo_best.pt", "thief_ppo.pt"]
        )
        path = next((models_dir / f for f in preferred if (models_dir / f).exists()), None)
        if path is None:
            _rl_policies[role] = None
            return None

        policy = RLPolicy._load_checkpoint(path, role, max_steps=35)
        _rl_policies[role] = policy
        logger.info(f"[strategy_tool] Loaded RL policy for {role} from {path}")
        return policy
    except Exception as e:
        logger.warning(f"[strategy_tool] RL policy load failed for {role}: {e}")
        _rl_policies[role] = None
        return None


@tool
def call_strategy(observation: dict) -> str:
    """Select a move using the trained RL policy for this role.

    Args:
        observation: Board state dict with keys:
            role, candidate_actions, own_position, scent_field, board_state, turn.

    Returns:
        Selected move: "NORTH", "SOUTH", "EAST", "WEST", or "STAY".

    Raises:
        RuntimeError: If no RL model is available (agent must choose without this tool).
    """
    role = observation.get("role", "cop")
    board_state = observation.get("board_state") or observation.get("grid_state") or {}

    policy = _load_rl_policy(role)
    if policy is not None and board_state:
        move = policy.select_move_from_dict(board_state)
        logger.info(f"[strategy_tool] RL policy → {move}")
        return move

    raise RuntimeError(
        f"No trained RL model found for role '{role}'. "
        "The agent should reason about the move directly from the board description."
    )
