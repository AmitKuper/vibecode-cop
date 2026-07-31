"""DQN agent for cop or thief role.

Uses a target network and experience replay for stable training.
Epsilon decays linearly from eps_start → eps_end over eps_decay_steps.
Both cop and thief are trained simultaneously in self-play; each maintains
its own replay buffer and target network.
"""

import random
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F  # noqa: N812

from agent.rl.networks import DQNNet
from agent.rl.replay_buffer import ReplayBuffer

N_ACTIONS = 5  # NORTH, SOUTH, EAST, WEST, STAY

# CPU is faster here: the env loop is Python/CPU-bound, so GPU transfers
# dominate over the tiny (196-input, 128-hidden) network compute.
# Switch to "cuda" only when using vectorized envs with large batch sizes.
_DEVICE = torch.device("cpu")


class DQNAgent:
    def __init__(
        self,
        role: str,
        grid_size: int = 7,
        lr: float = 1e-3,
        gamma: float = 0.99,
        eps_start: float = 1.0,
        eps_end: float = 0.05,
        eps_decay_steps: int = 20_000,
        buffer_size: int = 20_000,
        batch_size: int = 64,
        target_update_freq: int = 200,
        update_freq: int = 4,
        hidden: int = 128,
        net_type: str = "mlp",
    ):
        self.role = role
        self.gamma = gamma
        self.eps = eps_start
        self.eps_start = eps_start
        self.eps_end = eps_end
        self.eps_decay_steps = eps_decay_steps
        self.batch_size = batch_size
        self.target_update_freq = target_update_freq
        self.update_freq = update_freq
        self._steps = 0
        self._env_steps = 0  # counts every push, used for update_freq gating

        self.device = _DEVICE
        self.net = DQNNet(grid_size, N_ACTIONS, hidden, net_type).to(self.device)
        self.target_net = DQNNet(grid_size, N_ACTIONS, hidden, net_type).to(self.device)
        self.target_net.load_state_dict(self.net.state_dict())
        self.target_net.eval()

        self.optimizer = torch.optim.Adam(self.net.parameters(), lr=lr)
        self.buffer = ReplayBuffer(buffer_size)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def select_action(self, obs: list, training: bool = True) -> int:
        """Epsilon-greedy during training; greedy at inference."""
        if training and random.random() < self.eps:
            return random.randrange(N_ACTIONS)
        with torch.no_grad():
            t = self._to_tensor(obs)
            return int(self.net(t).argmax(dim=1).item())

    def push(self, obs: list, action: int, reward: float, next_obs: list, done: bool) -> None:
        self.buffer.push(obs, action, reward, next_obs, done)
        self._env_steps += 1

    def update(self) -> float | None:
        """Only runs a gradient step every update_freq environment steps."""
        if self._env_steps % self.update_freq != 0:
            return None
        """Sample from buffer and do one gradient step.

        Returns loss value or None if buffer is not yet warm.
        """
        if len(self.buffer) < self.batch_size:
            return None

        obs_b, act_b, rew_b, next_b, done_b = self.buffer.sample(self.batch_size)

        obs_t = torch.tensor(obs_b, dtype=torch.float32).to(self.device)
        next_t = torch.tensor(next_b, dtype=torch.float32).to(self.device)
        act_t = torch.tensor(act_b, dtype=torch.long).unsqueeze(1).to(self.device)
        rew_t = torch.tensor(rew_b, dtype=torch.float32).to(self.device)
        done_t = torch.tensor(done_b, dtype=torch.float32).to(self.device)

        q_vals = self.net(obs_t).gather(1, act_t).squeeze(1)

        with torch.no_grad():
            next_q = self.target_net(next_t).max(dim=1)[0]
            target = rew_t + self.gamma * next_q * (1.0 - done_t)

        loss = F.mse_loss(q_vals, target)
        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.net.parameters(), 10.0)
        self.optimizer.step()

        self._steps += 1
        frac = min(self._steps / self.eps_decay_steps, 1.0)
        self.eps = self.eps_start + frac * (self.eps_end - self.eps_start)

        if self._steps % self.target_update_freq == 0:
            self.target_net.load_state_dict(self.net.state_dict())

        return float(loss.item())

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        torch.save(
            {
                "role": self.role,
                "net": self.net.state_dict(),
                "target_net": self.target_net.state_dict(),
                "optimizer": self.optimizer.state_dict(),
                "steps": self._steps,
                "eps": self.eps,
            },
            path,
        )

    def load(self, path: str | Path) -> None:
        ckpt = torch.load(path, weights_only=False)
        self.net.load_state_dict(ckpt["net"])
        self.target_net.load_state_dict(ckpt["target_net"])
        self.optimizer.load_state_dict(ckpt["optimizer"])
        self._steps = ckpt["steps"]
        self.eps = ckpt["eps"]

    def _to_tensor(self, obs: list) -> torch.Tensor:
        return torch.tensor(obs, dtype=torch.float32).unsqueeze(0).to(self.device)
