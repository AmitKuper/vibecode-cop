"""Manifest-gated live-belief serving: filter evolves, resets, and only applies
when the artifact's obs_mode records uniform_belief=false."""

from __future__ import annotations

import numpy as np

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.live_belief import LiveBeliefPolicy, wants_live_belief


class _Entry:
    def __init__(self, obs_mode):
        self.obs_mode = obs_mode


def test_wants_live_belief_only_on_explicit_false():
    assert wants_live_belief(_Entry({"uniform_belief": False}))
    assert not wants_live_belief(_Entry({"uniform_belief": True}))
    assert not wants_live_belief(_Entry({}))
    assert not wants_live_belief(_Entry(None))


class _Inner:
    def __init__(self):
        self.beliefs = []
        self.resets = 0

    def reset(self):
        self.resets += 1

    def select_action(self, observation, belief, legal_actions):
        self.beliefs.append(belief)
        return legal_actions[0]


def _obs(scent, step):
    return LocalObservation(
        own_position=(0, 0),
        own_barriers_remaining=14,
        known_barriers=[],
        opponent_scent=scent,
        last_hint="",
        step=step,
        gamelet=1,
        grid_size=7,
    )


def _peaked(x, y):
    grid = [[0.0] * 7 for _ in range(7)]
    grid[y][x] = 0.9
    return grid


def test_live_filter_concentrates_and_is_not_uniform():
    policy = LiveBeliefPolicy(_Inner(), "cop")
    uniform = BeliefState.uniform(7, step=1)
    policy.select_action(_obs(_peaked(5, 5), 1), uniform, ["STAY"])
    served = policy.inner.beliefs[-1]
    assert not np.allclose(served.prob, uniform.prob)
    peak = np.unravel_index(np.asarray(served.prob).argmax(), (7, 7))
    assert peak == (5, 5)


def test_filter_evolves_across_steps_and_reset_restores_prior():
    inner = _Inner()
    policy = LiveBeliefPolicy(inner, "cop")
    uniform = BeliefState.uniform(7, step=1)
    policy.select_action(_obs(_peaked(5, 5), 1), uniform, ["STAY"])
    policy.select_action(_obs(_peaked(5, 4), 2), uniform, ["STAY"])
    assert not np.allclose(inner.beliefs[0].prob, inner.beliefs[1].prob)
    policy.reset()
    assert inner.resets == 1 and policy._engine is None
    policy.select_action(_obs(_peaked(1, 1), 1), uniform, ["STAY"])
    fresh_peak = np.unravel_index(np.asarray(inner.beliefs[-1].prob).argmax(), (7, 7))
    assert fresh_peak == (1, 1)


def test_loader_wraps_only_live_belief_artifacts(monkeypatch, tmp_path):
    from cop_worker.rl import counted_policy as cp

    class _FakeEntry:
        algorithm = "RecurrentA2C-GRU"
        obs_mode = {"uniform_belief": False, "scent_model": "multiplicative_book_v1"}

        def is_compatible(self, role, grid):
            return True, ""

    fake_inner = _Inner()
    monkeypatch.setattr("cop_worker.rl.model_schema.load_manifest", lambda p: {"cop": _FakeEntry()})
    monkeypatch.setattr(
        "cop_worker.rl.recurrent_policy.load_recurrent_policy", lambda p, r: fake_inner
    )
    monkeypatch.setattr(cp, "_guard_serving_obs_mode", lambda entry, role: None)
    wrapped = cp.load_counted_policy(tmp_path / "MANIFEST.json", "cop")
    assert isinstance(wrapped, LiveBeliefPolicy) and wrapped.inner is fake_inner

    _FakeEntry.obs_mode = {"uniform_belief": True}
    raw = cp.load_counted_policy(tmp_path / "MANIFEST.json", "cop")
    assert raw is fake_inner
