"""Historical-checkpoint opponent: replay a frozen earlier policy as the rival."""

from __future__ import annotations

import torch

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.types import DomainState
from cop_worker.observation import LocalObservation
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.local_obs_adapter import local_obs_to_tensor
from cop_worker.rl.recurrent_policy import RecurrentActorCritic


def _historical_action(
    state: DomainState,
    role: str,
    legal: list[str],
    historical_policy,
    opponent_scent: list[list[float]] | None,
    opponent_belief: BeliefEngine | None,
) -> str:
    if historical_policy is None:
        raise RuntimeError("historical-checkpoint opponent was not loaded")
    if isinstance(historical_policy, RecurrentActorCritic):
        own_pos = state.cop_position if role == "cop" else state.thief_position
        scent_for_obs = opponent_scent or [[0.0] * state.grid_size for _ in range(state.grid_size)]
        obs = LocalObservation(
            own_position=own_pos,
            own_barriers_remaining=state.cop_barriers_remaining if role == "cop" else 0,
            known_barriers=[tuple(item) for item in state.barriers],
            opponent_scent=scent_for_obs,
            last_hint="",
            step=state.turn + 1,
            gamelet=(state.turn % 6) + 1,
            grid_size=state.grid_size,
        )
        belief_state = (
            opponent_belief.belief
            if opponent_belief is not None
            else BeliefEngine(state.grid_size, role).belief
        )
        features = torch.tensor(local_obs_to_tensor(obs, belief_state), dtype=torch.float32)
        actions = COP_ACTIONS if role == "cop" else THIEF_ACTIONS
        action_mask = torch.tensor([a in legal for a in actions], dtype=torch.bool)
        with torch.no_grad():
            logits, _, _ = historical_policy(features.unsqueeze(0), None)
        masked_logits = logits.squeeze(0).masked_fill(~action_mask, -1e9)
        action = actions[int(masked_logits.argmax())]
        return action if action in legal else legal[0]
    from cop_worker.board import Board
    from cop_worker.rules_engine import RulesEngine

    board = Board(
        cop_position=list(state.cop_position),
        thief_position=list(state.thief_position),
        turn=state.turn,
        barriers=[list(item) for item in state.barriers],
        grid_size=state.grid_size,
    )
    rules = RulesEngine(board, max_turns=35)
    rules._scent_grid = [row[:] for row in state.scent_grid]
    historical_policy.barriers_remaining = state.cop_barriers_remaining
    observation = historical_policy._build_obs(
        board,
        rules,
        cop_scent_field=opponent_scent if role == "thief" else None,
    )
    action_index, _log_prob, _value = historical_policy.select_action(observation, training=False)
    action = (COP_ACTIONS if role == "cop" else THIEF_ACTIONS)[action_index]
    return action if action in legal else legal[0]
