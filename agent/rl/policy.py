"""Live-game policy wrapper for trained RL models (DQN or PPO).

Converts board state to observation, runs inference, returns a move string.
"""

from __future__ import annotations

import logging
from pathlib import Path

import torch

from agent.board import Board
from agent.rl.environment import ACTIONS, COP_ACTIONS
from agent.rl.observation import cop_observation, thief_observation
from agent.rules_engine import RulesEngine

logger = logging.getLogger(__name__)

_THIEF_IDX_TO_MOVE = dict(enumerate(ACTIONS))
_COP_IDX_TO_MOVE   = dict(enumerate(COP_ACTIONS))


class RLPolicy:
    """Role-specific inference wrapper around a saved DQN or PPO checkpoint."""

    def __init__(
        self,
        net: torch.nn.Module,
        role: str,
        algo: str,
        max_steps: int = 35,
        barrier_quota: int = 0,
        barriers_remaining: int = 0,
    ):
        self.net = net
        self.role = role
        self.algo = algo
        self.max_steps = max_steps
        self.barrier_quota = barrier_quota
        self.barriers_remaining = barriers_remaining
        self.device = next(net.parameters()).device
        self.net.eval()

    # --- Factory ---

    @classmethod
    def load(
        cls,
        role: str,
        models_dir: Path = Path("models"),
        algo: str | None = None,
        config_sha256: str | None = None,
        max_steps: int = 35,
    ) -> RLPolicy:
        """Load the best available model for a given role (first match wins)."""
        from agent.rl.policy_loader import load_checkpoint
        models_dir = Path(models_dir)
        candidates: list[Path] = []
        if algo and config_sha256:
            candidates.append(models_dir / f"{role}_{algo}_{config_sha256[:16]}.pt")
        if algo:
            candidates.append(models_dir / f"{role}_{algo}.pt")
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
        from agent.rl.policy_loader import load_checkpoint
        return load_checkpoint(path, role, max_steps)

    @staticmethod
    def _rebuild_net(
        state_dict: dict, ckpt: dict, algo: str, device: torch.device
    ) -> torch.nn.Module:
        """Backward-compatible static method delegating to policy_loader."""
        from agent.rl.policy_loader import rebuild_net
        return rebuild_net(state_dict, ckpt, algo, device)

    # --- Inference ---

    def select_move(
        self,
        board: Board,
        rules: RulesEngine,
        last_revealed_cop_pos: list[int] | None = None,
    ) -> str:
        """Return the best move string for the current board state."""
        obs = self._build_obs(board, rules, last_revealed_cop_pos=last_revealed_cop_pos)
        obs_t = torch.tensor(obs, dtype=torch.float32).unsqueeze(0).to(self.device)

        with torch.no_grad():
            if self.algo == "dqn":
                q = self.net(obs_t)
                action_idx = int(q.argmax(dim=1).item())
            else:
                logits, _ = self.net(obs_t)
                action_idx = int(torch.distributions.Categorical(logits=logits).sample().item())

        idx_map = _COP_IDX_TO_MOVE if (self.role == "cop" and self.barrier_quota > 0) else _THIEF_IDX_TO_MOVE  # noqa: E501
        move = idx_map.get(action_idx, "STAY")
        if move.startswith("PLACE_"):
            return move
        if not rules.validate_move(self.role, move):
            legal = board.get_legal_moves(self.role)
            move = legal[0] if legal else "STAY"
            logger.debug(f"[RLPolicy] Illegal move corrected → {move}")
        return move

    def select_action(self, obs: list, training: bool = False) -> tuple[int, float, float]:
        """PPOAgent-compatible interface for use as a frozen pool opponent."""
        obs_t = torch.tensor(obs, dtype=torch.float32).unsqueeze(0).to(self.device)
        with torch.no_grad():
            if self.algo == "dqn":
                q = self.net(obs_t)
                action_idx = int(q.argmax(dim=1).item())
            else:
                logits, _ = self.net(obs_t)
                dist = torch.distributions.Categorical(logits=logits)
                action_idx = int(dist.sample().item() if training else logits.argmax(dim=-1).item())
        return action_idx, 0.0, 0.0

    def select_move_from_dict(
        self,
        board_state: dict,
        rules: RulesEngine | None = None,
        last_revealed_cop_pos: list[int] | None = None,
    ) -> str:
        """Convenience wrapper accepting a board_state dict (from MCP messages)."""
        board = Board.from_dict(board_state)
        if rules is None:
            rules = RulesEngine(board)
        return self.select_move(board, rules, last_revealed_cop_pos=last_revealed_cop_pos)

    # --- Internal helpers ---

    def _build_obs(
        self,
        board: Board,
        rules: RulesEngine,
        last_revealed_cop_pos: list[int] | None = None,
    ) -> list:
        if self.role == "cop":
            return cop_observation(
                board, rules, self.max_steps,
                barriers_remaining=self.barriers_remaining,
                barrier_quota=self.barrier_quota,
            )
        return thief_observation(board, self.max_steps, last_revealed_cop_pos=last_revealed_cop_pos)
