"""hybrid_search_belief opt-in: oracle path unchanged, belief search on blind
frames with a peaked posterior, net fallback when flat, default mode untouched."""

from __future__ import annotations

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.search_policy import SearchRolePolicy, wrap_with_search

N = 7


class _Net:
    def __init__(self):
        self.calls = 0
        self.resets = 0

    def reset(self):
        self.resets += 1

    def select_action(self, observation, belief, legal):
        self.calls += 1
        return "STAY"


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


def _chebyshev_frame(x, y):
    """A frame with the unique 0.8 oracle peak the tracker resolves."""
    grid = [[0.0] * N for _ in range(N)]
    grid[y][x] = 0.8
    if x + 1 < N:
        grid[y][x + 1] = 0.5
    return grid


def _book_blanket(x, y):
    """A saturated book-style field: many 0.9 cells, no unique peak."""
    grid = [[0.0] * N for _ in range(N)]
    for yy in range(N):
        for xx in range(N):
            if abs(xx - x) + abs(yy - y) <= 3:
                grid[yy][xx] = 0.9
    return grid


def test_default_mode_is_byte_for_byte_unchanged():
    policy = SearchRolePolicy("cop", depth=2, fallback=_Net())
    assert policy.belief_mode is False and policy._belief_engine is None
    action = policy.select_action(
        _obs(_chebyshev_frame(4, 3)), BeliefState.uniform(N, step=5), ["N", "S", "E", "W", "STAY"]
    )
    assert action in {"N", "S", "E", "W", "STAY", "PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"}
    assert policy._belief_engine is None  # never engaged outside belief mode


def test_oracle_fix_still_wins_in_belief_mode():
    net = _Net()
    policy = SearchRolePolicy("cop", depth=2, fallback=net, belief_mode=True)
    action = policy.select_action(
        _obs(_chebyshev_frame(4, 0), own=(0, 0)),
        BeliefState.uniform(N, step=5),
        ["N", "S", "E", "W", "STAY"],
    )
    assert action == "E" and net.calls == 0  # exact search chased the fix


def test_blind_frame_with_peaked_posterior_uses_belief_search():
    net = _Net()
    policy = SearchRolePolicy("cop", depth=2, fallback=net, belief_mode=True)
    legal = ["N", "S", "E", "W", "STAY", "PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"]
    action = None
    for step in range(1, 7):  # repeated one-sided evidence concentrates the filter
        action = policy.select_action(
            _obs(_book_blanket(5, 5), own=(0, 0), step=step),
            BeliefState.uniform(N, step=step),
            legal,
        )
    assert net.calls == 0, "belief search should answer, not the net"
    assert action in ("E", "S", "PLACE_E", "PLACE_S")  # pressure toward the mass


def test_flat_posterior_falls_back_to_the_net():
    net = _Net()
    policy = SearchRolePolicy(
        "cop", depth=2, fallback=net, belief_mode=True, belief_peak_threshold=0.9
    )
    action = policy.select_action(
        _obs([[0.0] * N for _ in range(N)]),
        BeliefState.uniform(N, step=1),
        ["N", "STAY"],
    )
    assert action == "STAY" and net.calls == 1  # threshold unreachable -> net answers


def test_reset_clears_the_engine_and_wrap_flag_passthrough():
    net = _Net()
    policy = wrap_with_search(net, "police", {"max_steps": 35}, belief_mode=True)
    assert policy.belief_mode is True and policy.role == "cop"
    policy.select_action(
        _obs(_book_blanket(3, 3)), BeliefState.uniform(N, step=1), ["N", "STAY"]
    )
    assert policy._belief_engine is not None
    policy.reset()
    assert policy._belief_engine is None and net.resets == 1
    default = wrap_with_search(net, "police", {})
    assert default.belief_mode is False
