"""COPTHIEF_HUNT_MODE opt-in + the thief branch of SearchRolePolicy.

The hunt swap is config surface for real pairings (see committed_hunt.py):
it must engage only behind the env flag, and the default chain must not
even construct differently without it.
"""

from __future__ import annotations

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.search_policy import SearchRolePolicy

N = 7
COP_LEGAL = ["N", "S", "E", "W", "STAY", "PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"]
THIEF_LEGAL = ["N", "S", "E", "W", "STAY"]


def _obs(scent, own=(0, 0), step=5, walls=14):
    return LocalObservation(
        own_position=own,
        own_barriers_remaining=walls,
        known_barriers=[],
        opponent_scent=scent,
        last_hint="",
        step=step,
        gamelet=1,
        grid_size=N,
    )


def _frame(x, y):
    grid = [[0.0] * N for _ in range(N)]
    grid[y][x] = 0.8
    if x + 1 < N:
        grid[y][x + 1] = 0.5
    return grid


def test_default_chain_is_corridor(monkeypatch):
    monkeypatch.delenv("COPTHIEF_HUNT_MODE", raising=False)
    monkeypatch.delenv("COPTHIEF_COP_CHAIN", raising=False)
    assert SearchRolePolicy("cop")._cop_chain == "corridor"


def test_hunt_mode_alias_still_selects_hunt(monkeypatch):
    monkeypatch.delenv("COPTHIEF_COP_CHAIN", raising=False)
    monkeypatch.setenv("COPTHIEF_HUNT_MODE", "1")
    assert SearchRolePolicy("cop")._cop_chain == "hunt"


def test_plain_chain_skips_every_committed_plan(monkeypatch):
    monkeypatch.setenv("COPTHIEF_COP_CHAIN", "plain")
    policy = SearchRolePolicy("cop", depth=2)
    assert policy._cop_chain == "plain"
    for step in range(1, 12):  # a stalled dance: no plan may ever commit
        action = policy.select_action(
            _obs(_frame(2, 0), own=(0, 0), step=step),
            BeliefState.uniform(N, step=step),
            COP_LEGAL,
        )
        assert action in COP_LEGAL
    assert policy._hunt._line is None, "plain chain must never commit the hunt plan"


def test_hunt_chain_engages_behind_the_flag(monkeypatch):
    monkeypatch.setenv("COPTHIEF_COP_CHAIN", "hunt")
    policy = SearchRolePolicy("cop", depth=2)
    assert policy._cop_chain == "hunt"
    # a stalled dance at fixed distance: the hunt must eventually commit
    action = None
    for step in range(1, 12):
        action = policy.select_action(
            _obs(_frame(2, 0), own=(0, 0), step=step),
            BeliefState.uniform(N, step=step),
            COP_LEGAL,
        )
        assert action in COP_LEGAL
    assert policy._hunt._line is not None, "stalled chase must commit the hunt plan"
    assert action is not None


def test_thief_branch_runs_minimax_plus_escape():
    policy = SearchRolePolicy("thief", depth=2)
    action = policy.select_action(
        _obs(_frame(0, 0), own=(4, 4), step=3),
        BeliefState.uniform(N, step=3),
        THIEF_LEGAL,
    )
    assert action in THIEF_LEGAL


def test_thief_illegal_search_answer_falls_back_to_stay():
    policy = SearchRolePolicy("thief", depth=2)
    # only STAY is legal: whatever the search prefers must clamp legally
    action = policy.select_action(
        _obs(_frame(0, 0), own=(4, 4), step=3),
        BeliefState.uniform(N, step=3),
        ["STAY"],
    )
    assert action == "STAY"
