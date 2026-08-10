"""Recurrent research policies and checkpoint loading."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Protocol

import torch

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.types import DomainState
from cop_worker.rl.action_space import (
    COP_ACTIONS,
    THIEF_ACTIONS,
)
from cop_worker.rl.recurrent_policy import RecurrentActorCritic
from cop_worker.rl.research_evaluation.belief_search import belief_search_scores
from cop_worker.rl.train_recurrent import _legal, _observation
from cop_worker.scent import ScentFields


class ResearchPolicy(Protocol):
    """A policy receiving only role-local observation state."""

    role: str

    def reset(self, seed: int) -> None: ...

    def act(
        self,
        state: DomainState,
        scent: ScentFields,
        belief: BeliefEngine,
        rng: random.Random,
        gamelet: int,
    ) -> str: ...


def load_recurrent_network(path: str | Path, expected_role: str) -> RecurrentActorCritic:
    """Load a recurrent artifact directly and enforce its embedded schema."""
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if checkpoint.get("role") != expected_role:
        raise ValueError(f"{path} is not a {expected_role} checkpoint")
    if checkpoint.get("algorithm") != "RecurrentA2C-GRU":
        raise ValueError(f"unsupported recurrent algorithm in {path}")
    network = RecurrentActorCritic(
        int(checkpoint["input_size"]),
        int(checkpoint["n_actions"]),
        int(checkpoint["hidden_size"]),
    )
    network.load_state_dict(checkpoint["state_dict"])
    return network.eval()


class RecurrentResearchPolicy:
    """Stateful checkpoint inference with optional belief-search logit guidance."""

    def __init__(
        self,
        network: RecurrentActorCritic,
        role: str,
        temperature: float | None = None,
        search_strength: float = 0.0,
        search_depth: int = 1,
        search_particles: int = 8,
    ) -> None:
        self.network = network.eval()
        self.role = role
        self.temperature = temperature
        self.search_strength = float(search_strength)
        self.search_depth = int(search_depth)
        self.search_particles = int(search_particles)
        self.hidden: torch.Tensor | None = None
        self.generator = torch.Generator(device="cpu")
        # Per-episode inverse of the clamped wire scent law; inert unless
        # COPTHIEF_DECODED_SCENT=1. Rebuilt on reset() so no state leaks between games.
        self._decoder = None

    def reset(self, seed: int) -> None:
        self.hidden = None
        self.generator.manual_seed(seed)
        if self._decoder is not None:
            self._decoder.reset()

    def _scent_decoder(self, grid_size: int):
        from cop_worker.rl.obs_mode import decoded_scent_enabled
        from cop_worker.scent_decoder import EmitterDecoder

        if not decoded_scent_enabled():
            return None
        if self._decoder is None or self._decoder.n != grid_size:
            self._decoder = EmitterDecoder(grid_size)
        return self._decoder

    def act(
        self,
        state: DomainState,
        scent: ScentFields,
        belief: BeliefEngine,
        rng: random.Random,
        gamelet: int,
    ) -> str:
        legal = _legal(state, self.role)
        features, mask = _observation(
            state,
            self.role,
            scent,
            belief,
            legal,
            gamelet,
            decoder=self._scent_decoder(state.grid_size),
        )
        with torch.no_grad():
            logits, _value, self.hidden = self.network(features.unsqueeze(0), self.hidden)
        masked = logits.squeeze(0).masked_fill(~mask, -1e9)
        if self.search_strength:
            search = belief_search_scores(
                state,
                self.role,
                belief,
                legal,
                depth=self.search_depth,
                max_particles=self.search_particles,
            )
            search_tensor = torch.tensor(
                [search.get(action, -1e6) for action in self.actions], dtype=masked.dtype
            )
            finite = search_tensor > -1e5
            if bool(finite.any()):
                values = search_tensor[finite]
                scale = values.std(unbiased=False).clamp_min(0.25)
                search_tensor[finite] = (values - values.mean()) / scale
                masked = masked + self.search_strength * search_tensor
        if self.temperature is None:
            index = int(masked.argmax().item())
        else:
            probabilities = torch.softmax(masked / self.temperature, dim=-1)
            index = int(torch.multinomial(probabilities, 1, generator=self.generator).item())
        return self.actions[index]

    @property
    def actions(self) -> list[str]:
        return COP_ACTIONS if self.role == "cop" else THIEF_ACTIONS
