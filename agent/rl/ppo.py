"""PPO agent (actor-critic with GAE) for cop or thief role.

Collects a fixed-size rollout, then runs n_epochs of clipped surrogate updates.
Works naturally with simultaneous self-play: both agents collect experience
during the same rollout window, then each updates independently.

Key hyperparameters (defaults tuned for 7x7 board):
  rollout_size  — steps collected before each update (256)
  n_epochs      — PPO update epochs per rollout (4)
  clip_eps      — clipping range for probability ratio (0.2)
  gae_lambda    — GAE smoothing; 1.0 = MC returns, 0.0 = TD(0) (0.95)
  entropy_coef  — encourages exploration, prevents premature convergence (0.01)
"""

from __future__ import annotations

from pathlib import Path

import torch

from agent.rl.networks import PPONet
from agent.rl.ppo_update import PPOUpdateMixin
from agent.rl.rollout import _Rollout  # noqa: F401 (re-exported for backward compat)
from agent.rl.rollout import Rollout

N_ACTIONS = 5
N_COP_CHANNELS = 4  # default; 5 when barrier_quota > 0

# CPU is faster here: the env loop is Python/CPU-bound, so GPU transfers
# dominate over the tiny (196-input, 128-hidden) network compute.
# Switch to "cuda" only when using vectorized envs with large batch sizes.
_DEVICE = torch.device("cpu")


class PPOAgent(PPOUpdateMixin):
    def __init__(
        self,
        role: str,
        grid_size: int = 7,
        lr: float = 3e-4,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_eps: float = 0.2,
        n_epochs: int = 4,
        rollout_size: int = 256,
        entropy_coef: float = 0.01,
        value_coef: float = 0.5,
        max_grad_norm: float = 0.5,
        hidden: int = 128,
        net_type: str = "mlp",
        n_actions: int = N_ACTIONS,
        n_channels: int = 4,
    ):
        self.role = role
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.clip_eps = clip_eps
        self.n_epochs = n_epochs
        self.rollout_size = rollout_size
        self.entropy_coef = entropy_coef
        self.value_coef = value_coef
        self.max_grad_norm = max_grad_norm
        self._n_actions = n_actions
        self._n_channels = n_channels

        self.device = _DEVICE
        self.net = PPONet(
            grid_size, n_actions, hidden, net_type, in_channels=n_channels
        ).to(self.device)
        self.optimizer = torch.optim.Adam(self.net.parameters(), lr=lr, eps=1e-5)
        self._rollout = Rollout()
        self._updates = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def select_action(
        self, obs: list, training: bool = True
    ) -> tuple[int, float, float]:
        """Return (action, log_prob, value).

        At inference (training=False) picks the greedy action; during training
        samples from the policy distribution for exploration.
        """
        t = self._to_tensor(obs)
        with torch.no_grad():
            action, log_prob, _, value = self.net.get_action(t, deterministic=not training)
        return int(action.item()), float(log_prob.item()), float(value.squeeze().item())

    def push(
        self,
        obs: list,
        action: int,
        log_prob: float,
        reward: float,
        value: float,
        done: bool,
    ) -> None:
        self._rollout.push(obs, action, log_prob, reward, value, done)

    def ready_to_update(self) -> bool:
        return len(self._rollout) >= self.rollout_size

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        torch.save(
            {
                "role": self.role,
                "net": self.net.state_dict(),
                "optimizer": self.optimizer.state_dict(),
                "updates": self._updates,
                "n_actions": self._n_actions,
                "n_channels": self._n_channels,
            },
            path,
        )

    def load(self, path: str | Path) -> None:
        ckpt = torch.load(path, weights_only=False)
        saved_n_actions = ckpt.get("n_actions", 5)
        saved_n_channels = ckpt.get("n_channels", 4)
        if saved_n_actions != self._n_actions or saved_n_channels != self._n_channels:
            # Rebuild network to match the saved checkpoint's architecture
            state = ckpt["net"]
            first_w = state[next(iter(state))]
            grid_size = int((first_w.shape[1] / saved_n_channels) ** 0.5)
            hidden = first_w.shape[0]
            self._n_actions = saved_n_actions
            self._n_channels = saved_n_channels
            self.net = PPONet(
                grid_size, saved_n_actions, hidden, in_channels=saved_n_channels
            ).to(self.device)
            self.optimizer = torch.optim.Adam(self.net.parameters(), lr=3e-4, eps=1e-5)
        self.net.load_state_dict(ckpt["net"])
        self.optimizer.load_state_dict(ckpt["optimizer"])
        self._updates = ckpt["updates"]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _to_tensor(self, obs: list) -> torch.Tensor:
        return torch.tensor(obs, dtype=torch.float32).unsqueeze(0).to(self.device)
