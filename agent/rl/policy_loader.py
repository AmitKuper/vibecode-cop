"""Checkpoint loading and network reconstruction for RLPolicy.

Extracted from policy.py to keep each file under 150 lines.
"""

from __future__ import annotations

import logging
from pathlib import Path

import torch

logger = logging.getLogger(__name__)


def rebuild_net(state_dict: dict, ckpt: dict, algo: str, device: torch.device) -> torch.nn.Module:
    """Infer architecture from checkpoint metadata and state dict shapes."""
    from agent.rl.networks import DQNNet, PPONet

    n_actions = ckpt.get("n_actions")
    n_channels = ckpt.get("n_channels")

    first_key = next(iter(state_dict))
    first_w = state_dict[first_key]
    is_cnn = first_w.ndim == 4
    net_type = "cnn" if is_cnn else "mlp"

    if is_cnn:
        grid_size = ckpt.get("_grid_size", 7)
        if n_channels is None:
            n_channels = int(first_w.shape[1])
    else:
        flat_in = first_w.shape[1]
        if n_channels is None:
            for ch in (4, 5):
                gs = int((flat_in / ch) ** 0.5)
                if gs * gs * ch == flat_in:
                    n_channels = ch
                    break
            else:
                n_channels = 4
        grid_size = int((flat_in / n_channels) ** 0.5)

    if n_actions is None:
        head_key = "policy_head.weight" if algo == "ppo" else "head.weight"
        n_actions = state_dict[head_key].shape[0]

    hidden = first_w.shape[0] if not is_cnn else 256

    NetCls = PPONet if algo == "ppo" else DQNNet  # noqa: N806
    net = NetCls(
        grid_size=grid_size,
        n_actions=n_actions,
        hidden=hidden,
        net_type=net_type,
        in_channels=n_channels,
    )
    return net.to(device)


def load_checkpoint(path: Path, role: str, max_steps: int) -> RLPolicy:  # noqa: F821
    """Load a DQN or PPO checkpoint from disk and return an RLPolicy."""
    from agent.rl.policy import RLPolicy  # local import avoids circular dependency

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = torch.load(path, map_location=device, weights_only=False)

    algo = "ppo" if "updates" in ckpt else "dqn"
    net = rebuild_net(ckpt["net"], ckpt, algo, device)
    net.load_state_dict(ckpt["net"])
    net.eval()

    barrier_quota = ckpt.get("barrier_quota", 0)
    # If the model has 5 channels for cop but barrier_quota wasn't saved, infer it from game config.
    n_channels = ckpt.get("n_channels") or (
        int(next(iter(ckpt["net"].values())).shape[1])
        if next(iter(ckpt["net"].values())).ndim == 4
        else None
    )
    if role == "cop" and barrier_quota == 0 and n_channels == 5:
        try:
            from agent.config.shared_config import load_shared_config

            cfg = load_shared_config()
            barrier_quota = int(cfg.get("movement_and_barriers", {}).get("max_barriers", 14))
        except Exception:
            barrier_quota = 14
        logger.info(f"[RLPolicy] Inferred barrier_quota={barrier_quota} from 5-channel cop model")
    # Validate channel count against the current observation definition
    from agent.rl.observation import observation_shape as _obs_shape

    n_channels_ckpt = ckpt.get("n_channels") or n_channels
    expected_channels = _obs_shape(7, role, barrier_quota)[0]
    if n_channels_ckpt is not None and n_channels_ckpt != expected_channels:
        raise ValueError(
            f"Checkpoint channel mismatch for role='{role}': "
            f"model has {n_channels_ckpt} channels but current observation produces "
            f"{expected_channels} channels. Retrain or use a compatible checkpoint."
        )
    logger.info(f"[RLPolicy] Loaded {algo.upper()} {role} model from {path}")
    return RLPolicy(net, role=role, algo=algo, max_steps=max_steps, barrier_quota=barrier_quota)
