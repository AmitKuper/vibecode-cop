"""Neural network architectures for cop/thief RL agents.

Both DQN and PPO share the same CNN backbone (4 input channels, any grid size).
The backbone learns spatial features from the observation grid; role-specific
heads branch off for Q-values (DQN) or policy+value (PPO).
"""

import torch
import torch.nn as nn


class _MLPBackbone(nn.Module):
    """Fast flat MLP backbone — best for small boards (≤ 9×9) on CPU.

    Flattens the (C, H, W) observation to a vector and passes through two
    fully-connected layers. Trains ~10× faster than the CNN on CPU because
    there is no convolution overhead.
    """

    def __init__(self, grid_size: int = 7, in_channels: int = 4, hidden: int = 256):
        super().__init__()
        flat_in = in_channels * grid_size * grid_size
        self.net = nn.Sequential(
            nn.Flatten(),
            nn.Linear(flat_in, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
        )
        self.out_size = hidden

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class _CNNBackbone(nn.Module):
    """CNN feature extractor — better for large boards or when spatial patterns matter."""

    def __init__(self, grid_size: int = 7, in_channels: int = 4, hidden: int = 256):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Flatten(),
        )
        conv_out = 64 * grid_size * grid_size
        self.fc = nn.Sequential(
            nn.Linear(conv_out, hidden),
            nn.ReLU(),
        )
        self.out_size = hidden

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc(self.conv(x))


def _make_backbone(net_type: str, grid_size: int, hidden: int, in_channels: int = 4) -> nn.Module:
    if net_type == "cnn":
        return _CNNBackbone(grid_size, in_channels=in_channels, hidden=hidden)
    return _MLPBackbone(grid_size, in_channels=in_channels, hidden=hidden)


class DQNNet(nn.Module):
    """Q-network: obs → Q(s, a) for each action."""

    def __init__(
        self, grid_size: int = 7, n_actions: int = 5, hidden: int = 256, net_type: str = "mlp",
        in_channels: int = 4,
    ):
        super().__init__()
        self.backbone = _make_backbone(net_type, grid_size, hidden, in_channels)
        self.head = nn.Linear(self.backbone.out_size, n_actions)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.backbone(x))


class PPONet(nn.Module):
    """Actor-critic network: obs → (policy logits, state value)."""

    def __init__(
        self, grid_size: int = 7, n_actions: int = 5, hidden: int = 256, net_type: str = "mlp",
        in_channels: int = 4,
    ):
        super().__init__()
        self.backbone = _make_backbone(net_type, grid_size, hidden, in_channels)
        self.policy_head = nn.Linear(self.backbone.out_size, n_actions)
        self.value_head = nn.Linear(self.backbone.out_size, 1)

        # Orthogonal init — standard for PPO
        for layer in [self.policy_head, self.value_head]:
            nn.init.orthogonal_(layer.weight, gain=0.01)
            nn.init.zeros_(layer.bias)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        feat = self.backbone(x)
        return self.policy_head(feat), self.value_head(feat)

    def get_action(
        self, x: torch.Tensor, deterministic: bool = False
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Sample (or greedily pick) an action and return diagnostics.

        Returns:
            action, log_prob, entropy, value
        """
        logits, value = self(x)
        dist = torch.distributions.Categorical(logits=logits)
        action = logits.argmax(dim=-1) if deterministic else dist.sample()
        return action, dist.log_prob(action), dist.entropy(), value
