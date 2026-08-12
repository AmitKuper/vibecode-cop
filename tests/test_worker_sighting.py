"""Worker-path sighting contract — the cop gamelet must observe its REAL position and the
opponent's transmitted scent.

Regression guard for the blind-worker defect: ``_own_position`` used to be a hardcoded
placeholder ``(grid//2, grid//2)`` that was never updated, and ``_build_obs`` fed an
all-zero ``opponent_scent``. The cop therefore reasoned as if it stood at the centre of
the board, proposed moves the domain clamped to STAY, and froze on its start cell for the
whole game. These tests pin the fix: tracked position == canonical domain position, and
opponent scent actually reaches the observation.
"""

from __future__ import annotations

from cop_worker.state_machine import GameletState
from tests.helpers_worker_sighting import VALID_TERMS, _commit, _make_gamelet, _ScriptedPolicy


def test_own_position_seeded_from_terms_not_board_centre() -> None:
    """Tracked position starts at the agreed cop_start, never the centre-of-board stub."""
    g = _make_gamelet()
    assert g._own_position == (0, 0)
    assert g._own_position != (VALID_TERMS["board_size"] // 2,) * 2


def test_tracked_position_matches_canonical_domain_after_moves() -> None:
    """Applying our own committed moves advances the tracked position like the real board."""
    policy = _ScriptedPolicy(["E", "E", "S", "W"])
    g = _make_gamelet(policy)
    for step in range(1, 5):
        _commit(g, step)
    # (0,0) -E-> (1,0) -E-> (2,0) -S-> (2,1) -W-> (1,1)
    assert g._own_position == (1, 1)


def test_moves_clamp_at_board_edge() -> None:
    """A move off the board leaves the position unchanged (matches domain clamping)."""
    policy = _ScriptedPolicy(["N", "W"])  # both illegal from (0,0)
    g = _make_gamelet(policy)
    _commit(g, 1)
    _commit(g, 2)
    assert g._own_position == (0, 0)


def test_policy_observes_its_real_position_each_step() -> None:
    """The observation handed to the policy carries the true position, not a placeholder."""
    policy = _ScriptedPolicy(["E", "E", "E"])
    g = _make_gamelet(policy)
    for step in range(1, 4):
        _commit(g, step)
    assert [tuple(o.own_position) for o in policy.seen] == [(0, 0), (1, 0), (2, 0)]


def test_opponent_scent_reaches_observation() -> None:
    """A transmitted smell_grid lands in opponent_scent instead of an all-zero field."""
    policy = _ScriptedPolicy(["STAY", "STAY"])
    g = _make_gamelet(policy)
    _commit(g, 1)  # no smell yet
    assert all(v == 0.0 for row in policy.seen[0].opponent_scent for v in row)
    _commit(g, 2, smell_grid={"3,3": 0.9, "3,4": 0.45})
    scent = policy.seen[1].opponent_scent
    assert scent[3][3] == 0.9
    assert scent[3][4] == 0.45
    assert any(v > 0.0 for row in scent for v in row)


def test_worker_emits_own_scent_on_commit() -> None:
    """Our commit response carries our own book scent field, peaking at our position."""
    policy = _ScriptedPolicy(["STAY"])
    g = _make_gamelet(policy)
    resp = _commit(g, 1)
    smell = resp["response_payload"]["smell_grid"]
    assert smell, "worker must transmit a non-empty scent field"
    # Emitter cell is our position (0,0); scent grid is [row=y][col=x] -> key "y,x" = "0,0".
    assert smell["0,0"] == max(smell.values())
    assert g.state == GameletState.PLAYING


def test_duplicate_commit_for_same_step_does_not_advance_twice() -> None:
    """A retried/reordered commit for an already-advanced step must not move us twice."""
    policy = _ScriptedPolicy(["E", "E"])
    g = _make_gamelet(policy)
    _commit(g, 1)
    assert g._own_position == (1, 0)
    _commit(g, 1)  # peer retry for the same step
    assert g._own_position == (1, 0)


def test_duplicate_commit_does_not_double_spend_barrier_quota() -> None:
    """Barrier quota is not decremented twice by a retried commit for the same step."""
    policy = _ScriptedPolicy(["PLACE_E", "PLACE_E"])
    g = _make_gamelet(policy)
    before = g._own_barriers_remaining
    _commit(g, 1)
    _commit(g, 1)
    assert g._own_barriers_remaining == before - 1


def test_barrier_placement_records_barrier_and_forfeits_move() -> None:
    """PLACE_* consumes quota, records the cell, and does not move us."""
    policy = _ScriptedPolicy(["PLACE_E"])
    g = _make_gamelet(policy)
    before = g._own_barriers_remaining
    _commit(g, 1)
    assert g._own_position == (0, 0)
    assert [1, 0] in g._known_barriers
    assert g._own_barriers_remaining == before - 1
