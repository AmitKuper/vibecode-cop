"""Confidence-gated greedy+RL hybrid inference wrapper.

Wraps a trained ``RecurrentActorCritic`` and adds a belief-greedy logit bonus
to the policy head *at inference only*. The greedy prior (pursuit for cop,
evasion for thief) is decoded directly from the flat feature vector produced by
``local_obs_to_tensor``, so this wrapper is drop-in compatible with the
canonical ``evaluate`` tournament and the production ``select_action`` path.

Nothing here mutates the trainer or any saved weights: the base network is used
read-only and the greedy shaping is a pure function of the observation.
"""

from __future__ import annotations

import torch
import torch.nn as nn

from cop_worker.rl.action_space import COP_ACTIONS, MOVE_DELTAS, PLACE_DIRS, THIEF_ACTIONS
from cop_worker.rl.recurrent_policy import RecurrentActorCritic


def _belief_and_own(features: torch.Tensor, n: int) -> tuple[torch.Tensor, ...]:
    """Decode own (x, y), belief-argmax target (x, y) and confidence from features.

    Layout mirrors ``local_obs_to_tensor``: own one-hot occupies ``[0, n*n)`` and
    the Bayesian belief heatmap occupies ``[3*n*n, 4*n*n)``, both row-major over
    ``prob[y][x]``. Confidence is the final scalar feature.
    """
    own = features[:, : n * n]
    belief = features[:, 3 * n * n : 4 * n * n]
    own_idx = own.argmax(dim=1)
    tgt_idx = belief.argmax(dim=1)
    own_x, own_y = own_idx % n, own_idx // n
    t_x, t_y = tgt_idx % n, tgt_idx // n
    confidence = features[:, -1]
    return own_x, own_y, t_x, t_y, confidence


def greedy_scores(features: torch.Tensor, role: str, n: int) -> tuple[torch.Tensor, torch.Tensor]:
    """Return (scores[B, A], confidence[B]) replicating the belief-expert teacher.

    Scores match ``train_recurrent._belief_expert_action``: move toward (cop) or
    away from (thief) the highest-belief cell in Manhattan distance, a small STAY
    penalty, and for the cop a large bonus for dropping a barrier onto the target.
    """
    own_x, own_y, t_x, t_y, confidence = _belief_and_own(features, n)
    actions = COP_ACTIONS if role == "cop" else THIEF_ACTIONS
    scores = torch.zeros(features.shape[0], len(actions), device=features.device)
    own_dist = (own_x - t_x).abs() + (own_y - t_y).abs()
    for j, action in enumerate(actions):
        dx, dy = MOVE_DELTAS.get(action, (0, 0))
        dist = (own_x + dx - t_x).abs() + (own_y + dy - t_y).abs()
        value = (-dist if role == "cop" else dist).float()
        if action == "STAY":
            value = value - 0.05
        if role == "cop" and action in PLACE_DIRS:
            pdx, pdy = PLACE_DIRS[action]
            hit = ((own_x + pdx) == t_x) & ((own_y + pdy) == t_y)
            value = (-own_dist).float() + torch.where(hit, 20.0, -0.25)
        scores[:, j] = value
    return scores, confidence


class HybridActorCritic(nn.Module):
    """Adds a confidence-gated greedy bonus to a base actor-critic's logits.

    ``strength`` scales the overall bonus, ``conf_threshold`` gates it so the
    greedy prior is silent when the belief is diffuse (low confidence) and ramps
    to full weight as the belief peaks. ``clip`` bounds the centred greedy score
    so the cop's large trap bonus cannot swamp a well-trained policy.
    """

    def __init__(
        self,
        base: RecurrentActorCritic,
        role: str,
        grid_size: int = 7,
        strength: float = 1.0,
        conf_threshold: float = 0.0,
        clip: float = 6.0,
    ):
        super().__init__()
        self.base = base
        self.role = role
        self.n = grid_size
        self.strength = float(strength)
        self.conf_threshold = float(conf_threshold)
        self.clip = float(clip)

    def forward(
        self, features: torch.Tensor, hidden: torch.Tensor | None = None
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        logits, value, next_hidden = self.base(features, hidden)
        scores, confidence = greedy_scores(features, self.role, self.n)
        centred = (scores - scores.mean(dim=1, keepdim=True)).clamp(-self.clip, self.clip)
        denom = max(1.0 - self.conf_threshold, 1e-6)
        gate = ((confidence - self.conf_threshold) / denom).clamp(0.0, 1.0)
        bonus = (self.strength * gate).unsqueeze(1) * centred
        return logits + bonus, value, next_hidden
