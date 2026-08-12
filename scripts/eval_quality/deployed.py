"""Research-interface adapter over the PRODUCTION counted policy, plus audit constants."""

from __future__ import annotations

from pathlib import Path

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.action_space import (
    COP_ACTIONS,
    THIEF_ACTIONS,
    compute_legal_mask_cop,
    compute_legal_mask_thief,
)
from cop_worker.rl.counted_policy import load_counted_policy

REPO_ROOT = Path(__file__).resolve().parents[2]
COP_MANIFEST = REPO_ROOT / "models" / "MANIFEST.json"
THIEF_MANIFEST = REPO_ROOT.parent / "vibecode-thief" / "models" / "MANIFEST.json"

# Scripted families that can stand in as an opponent (historical_checkpoint needs a net).
OPPONENT_FAMILIES = (
    "random",
    "belief_pursuit_evasion",
    "wall",
    "local_adversarial_ensemble",
    "scent_following",
    "corridor_cutting",
    "anti_loop",
    "targeted_exploit",
    "deceptive_language",
)


class DeployedPolicy:
    """Research-interface adapter over the PRODUCTION counted policy.

    ``belief_mode``:
      ``prod``    -- ``BeliefState.uniform`` every step, mirroring RLMover/gamelet today.
      ``live``    -- the live Bayesian ``BeliefEngine`` belief, mirroring training.

    ``scent_mode`` is injected per-step by :func:`play` via ``self.scent_override``:
    ``None`` keeps the trainer's unclamped ``ScentFields``; a grid overrides it with the
    wire-clamped field.
    """

    def __init__(self, role: str, belief_mode: str = "prod", artifact: Path | None = None) -> None:
        self.role = role
        self.belief_mode = belief_mode
        self.scent_override: list[list[float]] | None = None
        if artifact is None:
            manifest = COP_MANIFEST if role == "cop" else THIEF_MANIFEST
            self.policy = load_counted_policy(manifest, role)
        else:
            # Un-manifested candidate: build the SAME production wrapper by hand so the
            # comparison against the champion is apples-to-apples.
            import torch

            from cop_worker.rl.recurrent_policy import RecurrentRolePolicy
            from cop_worker.rl.research_evaluation import load_recurrent_network

            net = load_recurrent_network(artifact, role)
            self.policy = RecurrentRolePolicy(net, role, torch.device("cpu"), "argmax")
        self.actions = COP_ACTIONS if role == "cop" else THIEF_ACTIONS

    def reset(self, seed: int) -> None:
        del seed
        self.policy.reset()

    def act(self, state, scent, belief, rng, gamelet):  # noqa: ANN001, ARG002
        own = state.cop_position if self.role == "cop" else state.thief_position
        scent_grid = self.scent_override
        if scent_grid is None:
            scent_grid = (
                scent.cop_observation_scent()
                if self.role == "cop"
                else scent.thief_observation_scent()
            )
        barriers = [tuple(b) for b in state.barriers]
        quota = state.cop_barriers_remaining if self.role == "cop" else 0
        obs = LocalObservation(
            own_position=(own[0], own[1]),
            own_barriers_remaining=quota,
            known_barriers=barriers,
            opponent_scent=scent_grid,
            last_hint="",
            step=state.turn + 1,
            gamelet=gamelet,
            grid_size=state.grid_size,
        )
        if self.belief_mode == "live":
            belief_state = belief.belief
        else:
            belief_state = BeliefState.uniform(state.grid_size, step=state.turn + 1)
        # Production masks with compute_legal_mask_*, not the canonical probe.
        if self.role == "cop":
            mask = compute_legal_mask_cop(tuple(own), barriers, quota, state.grid_size)
        else:
            mask = compute_legal_mask_thief(tuple(own), barriers, state.grid_size)
        legal = [a for a, m in zip(self.actions, mask, strict=True) if m] or list(self.actions)
        return self.policy.select_action(obs, belief_state, legal)
