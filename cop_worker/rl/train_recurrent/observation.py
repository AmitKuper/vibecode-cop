"""Policy-side observation tensor and deployable-action mask construction."""

from __future__ import annotations

import torch

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.types import DomainState
from cop_worker.observation import LocalObservation
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.local_obs_adapter import local_obs_to_tensor
from cop_worker.scent import ScentFields


def _observation(
    state: DomainState,
    role: str,
    scent: ScentFields,
    belief: BeliefEngine,
    legal: list[str],
    gamelet: int,
    risk_mask_enabled: bool = False,
    decoder=None,
) -> tuple[torch.Tensor, object]:
    own = state.cop_position if role == "cop" else state.thief_position
    scent_grid = scent.cop_observation_scent() if role == "cop" else scent.thief_observation_scent()
    obs = LocalObservation(
        own_position=own,
        own_barriers_remaining=state.cop_barriers_remaining if role == "cop" else 0,
        known_barriers=[tuple(item) for item in state.barriers],
        opponent_scent=scent_grid,
        last_hint="",
        step=state.turn + 1,
        gamelet=gamelet,
        grid_size=state.grid_size,
    )
    # Under COPTHIEF_UNIFORM_BELIEF=1 the student sees the frozen prior production feeds
    # instead of the live filter. Expert actions / risk masks below intentionally keep the
    # real belief: a privileged teacher with a blind student is the intended setup.
    from cop_worker.observation import BeliefState
    from cop_worker.rl.obs_mode import uniform_belief_enabled

    belief_input = (
        BeliefState.uniform(state.grid_size, step=state.turn + 1)
        if uniform_belief_enabled()
        else belief.belief
    )
    # ``decoder`` (per-episode, from the caller) applies the inverse of the clamped wire scent
    # law under COPTHIEF_DECODED_SCENT=1, so the student trains on the same decoded channels
    # production serves. Inert when None or when the switch is off.
    features = torch.tensor(local_obs_to_tensor(obs, belief_input, decoder), dtype=torch.float32)
    actions = COP_ACTIONS if role == "cop" else THIEF_ACTIONS
    deployable = legal
    if role == "thief" and risk_mask_enabled:
        from cop_worker.rl.risk_mask import belief_safe_actions

        deployable = belief_safe_actions(own, belief.belief, legal, list(state.barriers))
    mask = torch.tensor([action in deployable for action in actions], dtype=torch.bool)
    return features, mask
