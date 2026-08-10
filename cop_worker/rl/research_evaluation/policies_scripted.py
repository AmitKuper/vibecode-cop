"""Scripted, ensemble, and legacy research policies."""

from __future__ import annotations

import random
from pathlib import Path

import torch

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.types import DomainState
from cop_worker.rl.action_space import (
    COP_ACTIONS,
    THIEF_ACTIONS,
)
from cop_worker.rl.research_evaluation.policies_recurrent import ResearchPolicy
from cop_worker.rl.train_recurrent import _legal
from cop_worker.scent import ScentFields


class ScriptedResearchPolicy:
    """Adapter for the existing local-belief opponent families."""

    def __init__(self, role: str, family: str) -> None:
        if family == "historical_checkpoint":
            raise ValueError("historical checkpoint needs a real recurrent policy")
        self.role = role
        self.family = family

    def reset(self, seed: int) -> None:
        del seed

    def act(
        self,
        state: DomainState,
        scent: ScentFields,
        belief: BeliefEngine,
        rng: random.Random,
        gamelet: int,
    ) -> str:
        del gamelet
        from cop_worker.rl.train_recurrent import _opponent_action

        observed_scent = (
            scent.cop_observation_scent() if self.role == "cop" else scent.thief_observation_scent()
        )
        return _opponent_action(
            state,
            self.role,
            self.family,
            rng,
            opponent_scent=observed_scent,
            opponent_belief=belief,
        )


class GameletEnsemblePolicy:
    """Select a local policy by the public gamelet number."""

    def __init__(self, role: str, policies: dict[int, ResearchPolicy]) -> None:
        if set(policies) != set(range(1, 7)):
            raise ValueError("gamelet ensemble requires policies for gamelets 1..6")
        if any(policy.role != role for policy in policies.values()):
            raise ValueError("all gamelet policies must match the ensemble role")
        self.role = role
        self.policies = policies

    def reset(self, seed: int) -> None:
        for gamelet, policy in self.policies.items():
            policy.reset(seed + gamelet * 10_007)

    def act(
        self,
        state: DomainState,
        scent: ScentFields,
        belief: BeliefEngine,
        rng: random.Random,
        gamelet: int,
    ) -> str:
        return self.policies[gamelet].act(state, scent, belief, rng, gamelet)


class LegacyResearchPolicy:
    """Evaluate checked-in feed-forward PPO/DQN checkpoints on local scent."""

    def __init__(self, artifact: str | Path, role: str) -> None:
        from cop_worker.rl.policy_loader import load_checkpoint

        self.policy = load_checkpoint(Path(artifact), role, max_steps=35)
        self.role = role

    def reset(self, seed: int) -> None:
        torch.manual_seed(seed)
        self.policy.barriers_remaining = self.policy.barrier_quota

    def act(
        self,
        state: DomainState,
        scent: ScentFields,
        belief: BeliefEngine,
        rng: random.Random,
        gamelet: int,
    ) -> str:
        del belief, rng, gamelet
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
        if self.role == "cop":
            rules._scent_grid = scent.cop_observation_scent()
            observation = self.policy._build_obs(board, rules)
        else:
            observation = self.policy._build_obs(
                board,
                rules,
                cop_scent_field=scent.thief_observation_scent(),
            )
        tensor = torch.tensor(observation, dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            output = self.policy.net(tensor)
            logits = output[0] if isinstance(output, tuple) else output
        actions = COP_ACTIONS if logits.shape[-1] == len(COP_ACTIONS) else THIEF_ACTIONS
        legal = _legal(state, self.role)
        mask = torch.tensor([action in legal for action in actions], dtype=torch.bool)
        index = int(logits.squeeze(0).masked_fill(~mask, -1e9).argmax().item())
        return actions[index]
