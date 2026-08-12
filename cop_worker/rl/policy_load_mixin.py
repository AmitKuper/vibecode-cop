"""Checkpoint-discovery classmethods for ``RLPolicy``.

Split out of ``cop_worker.rl.policy`` (which remains the public facade);
``RLPolicy`` mixes this class in, so ``RLPolicy.load(...)`` is unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import torch

if TYPE_CHECKING:  # pragma: no cover - annotation-only import
    from cop_worker.rl.policy import RLPolicy


class PolicyLoadMixin:
    """Model discovery/loading surface delegating to ``policy_loader``."""

    @classmethod
    def load(
        cls,
        role: str,
        models_dir: Path = Path("models"),
        algo: str | None = None,
        config_sha256: str | None = None,
        max_steps: int = 35,
    ) -> RLPolicy:
        """Load the best available model for a given role (first match wins).

        Preference order (first existing file wins):
          1. Caller-specified algo+sha256 or algo name
          2. League best → league → ppo best → ppo (barrier-aware preferred)
          3. Full sorted glob fallback
        """
        from cop_worker.rl.policy_loader import load_checkpoint

        models_dir = Path(models_dir)
        candidates: list[Path] = []
        if algo and config_sha256:
            candidates.append(models_dir / f"{role}_{algo}_{config_sha256[:16]}.pt")
        if algo:
            candidates.append(models_dir / f"{role}_{algo}.pt")
        # Prefer league (barrier-aware, 5 channels) over plain ppo/dqn
        for preferred in (
            f"{role}_ppo_league_best.pt",
            f"{role}_ppo_league.pt",
            f"{role}_ppo_best.pt",
            f"{role}_ppo.pt",
        ):
            candidates.append(models_dir / preferred)
        candidates += sorted(models_dir.glob(f"{role}_*.pt"))
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            raise FileNotFoundError(
                f"No RL model found for role='{role}' in {models_dir}. "
                f"Run: python -m agent.rl.train --algo dqn"
            )
        return load_checkpoint(path, role, max_steps)

    @classmethod
    def _load_checkpoint(cls, path: Path, role: str, max_steps: int) -> RLPolicy:
        """Backward-compatible classmethod delegating to policy_loader."""
        from cop_worker.rl.policy_loader import load_checkpoint

        return load_checkpoint(path, role, max_steps)

    @staticmethod
    def _rebuild_net(
        state_dict: dict, ckpt: dict, algo: str, device: torch.device
    ) -> torch.nn.Module:
        """Backward-compatible static method delegating to policy_loader."""
        from cop_worker.rl.policy_loader import rebuild_net

        return rebuild_net(state_dict, ckpt, algo, device)
