"""``cop_worker.scent_chebyshev`` must reproduce the kit's own pinned bytes.

Fixture values are copied verbatim from the kit's ``vectors/pheromone.json`` (CORE) at
be96e57, so this suite fails if our port ever drifts from the reference arithmetic —
without importing the external repository at test time.
"""

from __future__ import annotations

from cop_worker.scent_chebyshev import (
    ChebyshevFields,
    ChebyshevTrail,
    chebyshev_decay,
    chebyshev_emit,
    field_to_grid,
)

# vectors/pheromone.json "emit" case 1: full 5x5 field, centre 0.9, falloff 0.3/step.
_EMIT_CENTER_FIELD = {
    "1,1": 0.3,
    "1,2": 0.3,
    "1,3": 0.3,
    "1,4": 0.3,
    "1,5": 0.3,
    "2,1": 0.3,
    "2,2": 0.6,
    "2,3": 0.6,
    "2,4": 0.6,
    "2,5": 0.3,
    "3,1": 0.3,
    "3,2": 0.6,
    "3,3": 0.9,
    "3,4": 0.6,
    "3,5": 0.3,
    "4,1": 0.3,
    "4,2": 0.6,
    "4,3": 0.6,
    "4,4": 0.6,
    "4,5": 0.3,
    "5,1": 0.3,
    "5,2": 0.3,
    "5,3": 0.3,
    "5,4": 0.3,
    "5,5": 0.3,
}

# vectors/pheromone.json "emit" case 2: corner emission clipped to board bounds.
_EMIT_CORNER_FIELD = {
    "0,0": 0.9,
    "0,1": 0.6,
    "0,2": 0.3,
    "1,0": 0.6,
    "1,1": 0.6,
    "1,2": 0.3,
    "2,0": 0.3,
    "2,1": 0.3,
    "2,2": 0.3,
}


def test_emit_matches_kit_center_fixture() -> None:
    assert chebyshev_emit((3, 3), 0.9, 5, 7) == _EMIT_CENTER_FIELD


def test_emit_matches_kit_corner_fixture() -> None:
    assert chebyshev_emit((0, 0), 0.9, 5, 7) == _EMIT_CORNER_FIELD


def test_decay_matches_kit_fixture() -> None:
    before = {"3,3": 0.9, "3,4": 0.6, "3,5": 0.3}
    assert chebyshev_decay(before, 0.1) == {"3,3": 0.8, "3,4": 0.5, "3,5": 0.2}


def test_decay_clamps_to_zero_at_the_floor() -> None:
    assert chebyshev_decay({"1,1": 0.05}, 0.1) == {"1,1": 0.0}


def test_trail_wire_snapshot_peaks_at_intensity_minus_decay() -> None:
    """Deposit-then-decay: the freshly-emitted centre crosses the wire at 0.8, not 0.9."""
    trail = ChebyshevTrail(7)
    wire = trail.full_turn((3, 3))
    assert wire["3,3"] == 0.8
    assert wire["3,4"] == 0.5
    assert wire["1,1"] == 0.2
    # Zero cells never cross the wire.
    assert all(v > 0.0 for v in wire.values())


def test_trail_merges_by_max_and_keeps_a_decaying_history() -> None:
    trail = ChebyshevTrail(7)
    trail.full_turn((3, 3))
    wire = trail.full_turn((3, 4))  # emitter stepped one column east
    # New centre re-peaks at 0.8; the old centre took a fresh 0.6 deposit (max over 0.7? no:
    # standing 0.8 - none; emit puts 0.6 at chebyshev-1 which does NOT beat standing 0.8),
    # so the old centre carries its decayed history: 0.8 - 0.1 = 0.7.
    assert wire["3,4"] == 0.8
    assert wire["3,3"] == 0.7
    # A never-visited far cell inside the new window carries only the new ring value.
    assert wire["3,6"] == 0.2


def test_trail_emit_gated_on_min_center_intensity() -> None:
    trail = ChebyshevTrail(7, emit_intensity=0.4, min_center_intensity=0.5)
    assert trail.full_turn((3, 3)) == {}


def test_trail_reset_clears_the_field() -> None:
    trail = ChebyshevTrail(7)
    trail.full_turn((3, 3))
    trail.reset()
    assert trail.snapshot() == {}


def test_field_to_grid_round_trip_and_junk_tolerance() -> None:
    grid = field_to_grid({"0,0": 0.9, "6,6": 0.3, "9,9": 1.0, "bad": 0.5}, 7)
    assert grid[0][0] == 0.9
    assert grid[6][6] == 0.3
    assert sum(sum(row) for row in grid) == 1.2  # out-of-board and junk keys dropped


def test_fields_observations_are_the_transmitted_snapshots() -> None:
    """Training observations must equal the post-decay wire fields, per role."""
    fields = ChebyshevFields.zeros(7)
    fields.update((0, 0), (3, 3))  # cop at x=0,y=0; thief at x=3,y=3
    cop_sees = fields.cop_observation_scent()
    thief_sees = fields.thief_observation_scent()
    # Cop sees the thief's trail: wire peak 0.8 at the thief's (row=3, col=3).
    assert cop_sees[3][3] == 0.8
    # Thief sees the cop's trail: wire peak 0.8 at the cop's (row=0, col=0).
    assert thief_sees[0][0] == 0.8
    # And the roles are not crossed.
    assert cop_sees[0][0] in (0.0, 0.2)  # only a ring of the thief's field could reach here
    assert thief_sees[3][3] in (0.0, 0.2)
