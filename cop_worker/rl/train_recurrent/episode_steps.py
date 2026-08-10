"""Small mechanical steps of an episode: ablations, metrics, belief advancement."""

from __future__ import annotations

import torch

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.types import DomainState
from cop_worker.scent import ScentFields


def _ablate_features(features: torch.Tensor, feature_mode: str, grid_cells: int) -> None:
    """Zero the ablated channels in place; ``full`` is a no-op."""
    if feature_mode == "no_scent":
        features[2 * grid_cells : 3 * grid_cells] = 0.0
    elif feature_mode == "no_belief":
        features[3 * grid_cells : 4 * grid_cells] = 0.0
        features[-2:] = 0.0
    elif feature_mode != "full":
        raise RuntimeError(f"unsupported feature ablation {feature_mode!r}")


def _note_choice_metrics(
    episode_metrics: dict[str, int] | None,
    legal: list[str],
    mask: torch.Tensor,
    actions: tuple[str, ...],
) -> None:
    if episode_metrics is None:
        return
    episode_metrics["legal_candidates"] = episode_metrics.get("legal_candidates", 0) + len(legal)
    episode_metrics["risk_pruned"] = episode_metrics.get("risk_pruned", 0) + sum(
        action in legal and not bool(mask[index]) for index, action in enumerate(actions)
    )


def _note_decision_metrics(
    episode_metrics: dict[str, int] | None, action: str, legal: list[str]
) -> None:
    if episode_metrics is None:
        return
    episode_metrics["decisions"] = episode_metrics.get("decisions", 0) + 1
    episode_metrics["illegal_selected"] = episode_metrics.get("illegal_selected", 0) + int(
        action not in legal
    )


def _note_barrier_metric(episode_metrics: dict[str, int] | None, cop_action: str) -> None:
    if episode_metrics is None:
        return
    episode_metrics["barrier_placements"] = episode_metrics.get("barrier_placements", 0) + int(
        cop_action.startswith("PLACE_")
    )


def _step_reward(
    role: str,
    outcome: str,
    previous_distance: int,
    current_distance: int,
    previous_barriers: list[tuple[int, int]],
    state: DomainState,
    belief: BeliefEngine,
) -> tuple[bool, str | None, float]:
    """Terminal flag, winner (terminal only), and the dense step reward."""
    from cop_worker.rl.train_recurrent.sim import _belief_trap_reward

    if outcome != "ongoing":
        winner = "cop" if "cop" in outcome else "thief"
        return True, winner, 8.0 if winner == role else -8.0
    delta = previous_distance - current_distance
    reward = (0.12 * delta if role == "cop" else -0.12 * delta) - 0.01
    if role == "cop":
        reward += _belief_trap_reward(
            belief.belief, previous_barriers, list(state.barriers), state.grid_size
        )
    return False, None, reward


def _advance_beliefs(
    scent: ScentFields,
    state: DomainState,
    role: str,
    opponent_role: str,
    belief: BeliefEngine,
    opponent_belief: BeliefEngine,
) -> tuple[ScentFields, BeliefEngine, BeliefEngine]:
    """Advance the scent fields and both Bayesian filters one post-transition step."""
    scent = scent.update(state.cop_position, state.thief_position)
    barriers = [tuple(item) for item in state.barriers]
    observed_scent = (
        scent.cop_observation_scent() if role == "cop" else scent.thief_observation_scent()
    )
    belief = belief.predict(barriers).observe_scent(observed_scent, barriers)
    updated_opponent_scent = (
        scent.thief_observation_scent()
        if opponent_role == "thief"
        else scent.cop_observation_scent()
    )
    opponent_belief = opponent_belief.predict(barriers).observe_scent(
        updated_opponent_scent, barriers
    )
    return scent, belief, opponent_belief
