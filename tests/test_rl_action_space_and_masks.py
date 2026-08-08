"""Fast unit tests for legal-action masking, action sampling, obs adapter, risk mask.

Pure numeric logic — no LLM, no network.
"""

from __future__ import annotations

import numpy as np

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.action_space import (
    COP_ACTIONS,
    THIEF_ACTIONS,
    compute_legal_mask_cop,
    compute_legal_mask_thief,
    mask_logits,
    sample_action,
)
from cop_worker.rl.local_obs_adapter import local_obs_to_tensor, obs_tensor_shape
from cop_worker.rl.risk_mask import belief_risk_score, belief_safe_actions

N = 7


def _idx(actions, name):
    return actions.index(name)


# --- legal masks ------------------------------------------------------------

def test_cop_mask_corner_blocks_offboard_moves():
    mask = compute_legal_mask_cop((0, 0), barriers=[], barriers_remaining=2, grid_size=N)
    assert not mask[_idx(COP_ACTIONS, "N")]  # off top
    assert not mask[_idx(COP_ACTIONS, "W")]  # off left
    assert mask[_idx(COP_ACTIONS, "S")] and mask[_idx(COP_ACTIONS, "E")]
    assert mask[_idx(COP_ACTIONS, "STAY")]
    # placements ahead that stay on-board are legal when quota remains
    assert mask[_idx(COP_ACTIONS, "PLACE_S")] and mask[_idx(COP_ACTIONS, "PLACE_E")]
    assert not mask[_idx(COP_ACTIONS, "PLACE_N")]  # off-board target


def test_cop_mask_no_placement_without_quota():
    mask = compute_legal_mask_cop((3, 3), barriers=[], barriers_remaining=0, grid_size=N)
    for name in ("PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"):
        assert not mask[_idx(COP_ACTIONS, name)]


def test_cop_mask_blocked_by_barrier():
    mask = compute_legal_mask_cop((3, 3), barriers=[(4, 3)], barriers_remaining=2, grid_size=N)
    assert not mask[_idx(COP_ACTIONS, "E")]  # (4,3) blocked
    assert not mask[_idx(COP_ACTIONS, "PLACE_E")]  # cannot place on existing barrier


def test_thief_mask_shape_and_center_all_legal():
    mask = compute_legal_mask_thief((3, 3), barriers=[], grid_size=N)
    assert len(mask) == len(THIEF_ACTIONS)
    assert mask.all()


# --- mask_logits / sample_action -------------------------------------------

def test_mask_logits_sets_illegal_very_negative():
    logits = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    mask = np.array([True, False, True, False, True])
    masked = mask_logits(logits, mask)
    assert masked[1] <= -1e9 and masked[3] <= -1e9
    assert masked[0] == 1.0 and masked[4] == 5.0


def test_sample_action_argmax_respects_mask():
    logits = np.array([10.0, 0.0, 0.0, 0.0, 0.0])  # illegal action has the top logit
    mask = np.array([False, True, True, True, True])
    chosen = sample_action(logits, mask, mode="argmax")
    assert chosen != 0 and mask[chosen]


def test_sample_action_softmax_stays_legal():
    np.random.seed(0)
    logits = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    mask = np.array([True, False, True, False, True])
    for _ in range(30):
        chosen = sample_action(logits, mask, mode="sample", temperature=1.0)
        assert mask[chosen]


# --- local_obs_adapter ------------------------------------------------------

def _obs(own):
    return LocalObservation(
        own_position=own,
        own_barriers_remaining=2,
        known_barriers=[(0, 0)],
        opponent_scent=[[0.0] * N for _ in range(N)],
        last_hint="",
        step=5,
        gamelet=2,
        grid_size=N,
    )


def test_obs_tensor_shape_and_layout():
    assert obs_tensor_shape(N) == 4 * N * N + 5
    belief = BeliefState.uniform(N)
    vec = local_obs_to_tensor(_obs((2, 3)), belief)
    assert vec.shape == (obs_tensor_shape(N),)
    # own one-hot lives in the first N*N block at index y*N + x
    assert vec[3 * N + 2] == 1.0
    # last scalar feature is belief confidence (0.0 for a uniform belief)
    assert vec[-1] == belief.confidence


# --- risk_mask --------------------------------------------------------------

def test_belief_safe_actions_never_empties_and_subsets():
    belief = BeliefState.uniform(N)
    legal = list(THIEF_ACTIONS)
    safe = belief_safe_actions((3, 3), belief, legal, barriers=[], keep_fraction=0.6)
    assert 0 < len(safe) <= len(legal)
    assert set(safe).issubset(set(legal))


def test_belief_safe_actions_empty_when_no_legal():
    belief = BeliefState.uniform(N)
    assert belief_safe_actions((3, 3), belief, [], barriers=[]) == []


def test_belief_risk_score_higher_near_belief_mass():
    prob = np.zeros((N, N))
    prob[3][3] = 1.0
    belief = BeliefState(grid_size=N, prob=prob).normalize()
    near = belief_risk_score((3, 3), belief, barriers=[])
    far = belief_risk_score((6, 6), belief, barriers=[])
    assert near > far  # proximity to believed opponent raises risk
