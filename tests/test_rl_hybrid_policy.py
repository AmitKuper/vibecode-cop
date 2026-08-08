"""Fast unit tests for the confidence-gated greedy+RL hybrid wrapper.

Pure tensor logic — no LLM, no network, no disk. Verifies that the greedy prior
is decoded correctly from the observation feature vector and that the gate makes
the bonus vanish below the confidence threshold.
"""

from __future__ import annotations

import numpy as np
import torch

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from cop_worker.rl.hybrid_policy import HybridActorCritic, greedy_scores
from cop_worker.rl.local_obs_adapter import local_obs_to_tensor, obs_tensor_shape
from cop_worker.rl.recurrent_policy import RecurrentActorCritic

N = 7


def _features(own, target, confidence):
    """Build a real feature vector with a belief peaked at `target`."""
    prob = np.zeros((N, N))
    prob[target[1], target[0]] = 1.0  # prob is indexed [y][x]
    belief = BeliefState(grid_size=N, prob=prob, entropy=0.0, confidence=confidence)
    obs = LocalObservation(
        own_position=own,
        own_barriers_remaining=3,
        known_barriers=[],
        opponent_scent=[[0.0] * N for _ in range(N)],
        last_hint="",
        step=1,
        gamelet=1,
        grid_size=N,
    )
    return torch.tensor(local_obs_to_tensor(obs, belief), dtype=torch.float32).unsqueeze(0)


def _base(role):
    n_actions = len(COP_ACTIONS if role == "cop" else THIEF_ACTIONS)
    torch.manual_seed(0)
    return RecurrentActorCritic(obs_tensor_shape(N), n_actions, hidden_size=16).eval()


def test_greedy_scores_decode_own_and_target():
    feats = _features(own=(0, 0), target=(6, 0), confidence=0.8)
    scores, conf = greedy_scores(feats, "cop", N)
    assert scores.shape == (1, len(COP_ACTIONS))
    assert abs(float(conf.item()) - 0.8) < 1e-6


def test_cop_prior_prefers_moving_toward_belief():
    feats = _features(own=(0, 0), target=(6, 0), confidence=0.9)
    hybrid = HybridActorCritic(_base("cop"), "cop", grid_size=N, strength=2.0, conf_threshold=0.0)
    base_logits, _, _ = hybrid.base(feats, None)
    hyb_logits, _, _ = hybrid(feats, None)
    bonus = (hyb_logits - base_logits).squeeze(0)
    e, w = COP_ACTIONS.index("E"), COP_ACTIONS.index("W")
    # Target is due east of own → moving E must be favoured over W.
    assert bonus[e] > bonus[w]


def test_thief_prior_prefers_moving_away_from_belief():
    feats = _features(own=(0, 0), target=(6, 0), confidence=0.9)
    hybrid = HybridActorCritic(
        _base("thief"), "thief", grid_size=N, strength=2.0, conf_threshold=0.0
    )
    base_logits, _, _ = hybrid.base(feats, None)
    hyb_logits, _, _ = hybrid(feats, None)
    bonus = (hyb_logits - base_logits).squeeze(0)
    e, w = THIEF_ACTIONS.index("E"), THIEF_ACTIONS.index("W")
    # Pursuer is due east → thief should be pushed W (away), not E.
    assert bonus[w] > bonus[e]


def test_gate_silences_bonus_below_threshold():
    feats = _features(own=(0, 0), target=(6, 0), confidence=0.2)
    hybrid = HybridActorCritic(_base("cop"), "cop", grid_size=N, strength=2.0, conf_threshold=0.5)
    base_logits, _, _ = hybrid.base(feats, None)
    hyb_logits, _, _ = hybrid(feats, None)
    # confidence 0.2 < threshold 0.5 → gate 0 → hybrid logits identical to base.
    assert torch.allclose(hyb_logits, base_logits, atol=1e-6)


def test_cop_place_bonus_when_barrier_lands_on_target():
    # Own at (0,0), target adjacent east (1,0): PLACE_E drops a barrier onto the target.
    feats = _features(own=(0, 0), target=(1, 0), confidence=1.0)
    scores, _ = greedy_scores(feats, "cop", N)
    row = scores.squeeze(0)
    place_e = COP_ACTIONS.index("PLACE_E")
    place_w = COP_ACTIONS.index("PLACE_W")
    # Dropping the barrier on the believed thief cell is the strongly-preferred action.
    assert row[place_e] == row.max()
    assert row[place_e] > row[place_w]


def test_forward_preserves_shapes_and_hidden():
    feats = _features(own=(2, 2), target=(4, 4), confidence=0.5)
    hybrid = HybridActorCritic(_base("cop"), "cop", grid_size=N, strength=1.0, conf_threshold=0.0)
    logits, value, hidden = hybrid(feats, None)
    assert logits.shape == (1, len(COP_ACTIONS))
    assert value.shape == (1, 1)
    assert hidden.shape == (1, 16)
