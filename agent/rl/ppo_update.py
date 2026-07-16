"""PPO update logic: GAE computation and surrogate loss training step.

Extracted from ppo.py to keep each file under 150 lines.
Used as a mixin by PPOAgent.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F  # noqa: N812


class PPOUpdateMixin:
    """Mixin providing GAE computation and PPO surrogate update.

    Requires the host class to have:
        self._rollout   — Rollout instance
        self.net        — PPONet
        self.optimizer  — torch optimizer
        self.device     — torch.device
        self.gamma, self.gae_lambda, self.clip_eps,
        self.n_epochs, self.value_coef, self.entropy_coef,
        self.max_grad_norm  — hyperparameters
        self._updates   — int counter
    """

    def update(self, last_obs: list, last_done: bool) -> dict | None:
        """Run PPO update on collected rollout.

        Args:
            last_obs:  Observation after the final rollout step (for bootstrapping).
            last_done: Whether the episode ended at the final step.

        Returns:
            Dict with mean losses across epochs, or None if rollout is empty.
        """
        if len(self._rollout) == 0:
            return None

        advantages = self._compute_gae(last_obs, last_done)
        returns = (
            advantages + torch.tensor(self._rollout.values, dtype=torch.float32)
        ).to(self.device)

        obs_t = torch.tensor(self._rollout.obs, dtype=torch.float32).to(self.device)
        acts_t = torch.tensor(self._rollout.actions, dtype=torch.long).to(self.device)
        old_lp_t = torch.tensor(self._rollout.log_probs, dtype=torch.float32).to(self.device)
        adv_t = (advantages.to(self.device) - advantages.mean()) / (advantages.std() + 1e-8)

        total = {"policy": 0.0, "value": 0.0, "entropy": 0.0}

        for _ in range(self.n_epochs):
            logits, values = self.net(obs_t)
            dist = torch.distributions.Categorical(logits=logits)
            log_probs = dist.log_prob(acts_t)
            entropy = dist.entropy().mean()

            ratio = (log_probs - old_lp_t).exp()
            s1 = ratio * adv_t
            s2 = ratio.clamp(1.0 - self.clip_eps, 1.0 + self.clip_eps) * adv_t
            policy_loss = -torch.min(s1, s2).mean()
            value_loss = F.mse_loss(values.squeeze(1), returns)

            loss = policy_loss + self.value_coef * value_loss - self.entropy_coef * entropy
            self.optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(self.net.parameters(), self.max_grad_norm)
            self.optimizer.step()

            total["policy"] += float(policy_loss.item())
            total["value"] += float(value_loss.item())
            total["entropy"] += float(entropy.item())

        self._rollout.clear()
        self._updates += 1
        return {k: v / self.n_epochs for k, v in total.items()}

    def _compute_gae(self, last_obs: list, last_done: bool) -> torch.Tensor:
        """Generalized Advantage Estimation (Schulman et al., 2015)."""
        with torch.no_grad():
            last_t = self._to_tensor(last_obs)
            _, last_value_t = self.net(last_t)
            last_value = 0.0 if last_done else float(last_value_t.squeeze().item())

        T = len(self._rollout)  # noqa: N806
        advantages = [0.0] * T
        gae = 0.0

        for t in reversed(range(T)):
            if self._rollout.dones[t]:
                next_value = 0.0
                gae = 0.0
            else:
                next_value = self._rollout.values[t + 1] if t < T - 1 else last_value

            delta = self._rollout.rewards[t] + self.gamma * next_value - self._rollout.values[t]
            gae = delta + self.gamma * self.gae_lambda * gae
            advantages[t] = gae

        return torch.tensor(advantages, dtype=torch.float32)
