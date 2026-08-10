"""Gamelet move + commitment generation (mixin)."""

from __future__ import annotations

import logging
import random
import secrets

from cop_worker.crypto import build_commitment
from cop_worker.gamelet_constants import _COP_ACTIONS

logger = logging.getLogger(__name__)


class GameletMoveMixin:
    """Move selection and commitment construction."""

    def _generate_move(self) -> dict:
        """Generate a move action for the cop (police) role.

        Uses the RL policy if available, with random fallback on any error.

        Returns:
            Action dict with a direction or barrier placement.
        """
        if self._policy is not None:
            try:
                from cop_worker.rl.action_space import COP_ACTIONS, compute_legal_mask_cop

                obs, belief = self._build_obs()
                # Pass the TRUE legal action set (board edges + barriers + quota), matching how
                # the policy was trained. Passing the full list let the policy propose off-board
                # moves (e.g. N from the top row) that the domain clamps to STAY — freezing the
                # cop at its start cell. See compute_legal_mask_cop.
                mask = compute_legal_mask_cop(
                    tuple(obs.own_position),
                    list(obs.known_barriers),
                    obs.own_barriers_remaining,
                    obs.grid_size,
                )
                legal = [a for a, m in zip(COP_ACTIONS, mask, strict=True) if m] or list(
                    COP_ACTIONS
                )
                action_name = self._policy.select_action(obs, belief, legal)
                return self._action_to_dict(action_name)
            except Exception as exc:
                logger.warning("RL policy inference failed, falling back to random: %s", exc)
        direction = random.choice(_COP_ACTIONS)
        return {"type": "move", "direction": direction}

    def _generate_commitment(self, action: dict) -> tuple[str, str]:
        """Generate a nonce and commitment hash for the given action.

        Args:
            action: Action dict to commit to.

        Returns:
            Tuple of (nonce, commitment_hash) where nonce is kept secret until reveal.
        """
        nonce = secrets.token_hex(32)
        commitment_hash = build_commitment(nonce, action)
        return nonce, commitment_hash
