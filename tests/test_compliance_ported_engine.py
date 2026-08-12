"""Compliance tests verifying mandatory project rules (hidden info, scent, turn limits)."""

import pytest

from cop_worker.board import Board
from cop_worker.rules_engine import RulesEngine

# ---------------------------------------------------------------------------
# Hidden-information: LocalObservation has no opponent_position
# ---------------------------------------------------------------------------


def test_local_observation_has_no_opponent_position():
    """LocalObservation must NOT expose opponent raw coordinates."""
    from cop_worker.observation import LocalObservation

    obs = LocalObservation(
        own_position=(1, 2),
        own_barriers_remaining=0,
        known_barriers=[],
        opponent_scent=[[0.0] * 7 for _ in range(7)],
        last_hint="",
        step=3,
        gamelet=1,
        grid_size=7,
    )
    d = obs.__dict__
    assert "opponent_position" not in d
    assert "thief_position" not in d
    assert "cop_position" not in d
    assert "own_position" in d


# ---------------------------------------------------------------------------
# Scent: accumulated and decaying over turns
# ---------------------------------------------------------------------------


def _make_rules() -> tuple[Board, RulesEngine]:
    board = Board(cop_position=[0, 0], thief_position=[3, 3])
    return board, RulesEngine(board)


def test_scent_accumulates_after_moves():
    """Scent must persist across turns, not reset to zero each call."""
    board, rules = _make_rules()
    initial = rules.get_scent_field()
    assert all(v == 0.0 for row in initial for v in row), "Scent must start at zero"

    rules.apply_moves("STAY", "SOUTH")
    after_one = rules.get_scent_field()
    tx, ty = board.thief_position
    assert after_one[ty][tx] == pytest.approx(0.9, abs=0.01), (
        "Scent center must equal SCENT_CENTER at thief's position"
    )


def test_scent_decays_when_thief_moves_away():
    """Old scent follows the book model (multiplicative_book_v1), verified byte-exact vs the
    league kit's ``book_full_turn`` oracle: ``tau' = min(0.9, max(0, 0.9*old + emission))``.

    A cell still inside the 5x5 emission field is re-emitted and holds at the 0.9 ceiling;
    a cell the thief has left OUT of range decays purely multiplicatively (x0.9 per turn).
    (This replaces the pre-book additive expectation of ``0.9*0.9 + 0.62 = 1.43``, which the
    kit's registered book model does not produce.)
    """
    board, rules = _make_rules()
    rules.apply_moves("STAY", "STAY")
    field_before = rules.get_scent_field()
    assert field_before[3][3] == pytest.approx(0.9, abs=0.01)
    # A far cell inside the 5x5 field at deposit time (chebyshev 2 from (3,3)).
    far_before = field_before[5][3]
    assert far_before == pytest.approx(0.20, abs=0.01)

    rules.apply_moves("STAY", "NORTH")  # thief 3,3 -> 3,2
    field_after = rules.get_scent_field()
    # (3,3) is now adjacent to the thief: re-emitted, so min(0.9, 0.9*0.9 + 0.62) = 0.9 ceiling.
    assert field_after[3][3] == pytest.approx(0.9, abs=0.01), (
        "book model clamps re-emitted scent to the 0.9 emission ceiling"
    )
    assert field_after[3][3] <= 0.9 + 1e-9, "book model bounds scent at the 0.9 ceiling"
    # (3,5) is now out of the thief's 5x5 field: pure multiplicative decay x0.9.
    assert field_after[5][3] == pytest.approx(0.9 * far_before, abs=0.01), (
        "old scent out of range must decay multiplicatively (x0.9), not vanish or persist"
    )
    assert field_after[5][3] < far_before, "scent must decay once the thief has moved away"


def test_fresh_snapshot_unchanged_for_rl():
    """compute_scent_field() must still return a fresh snapshot (RL backward compat)."""
    board, rules = _make_rules()
    tx, ty = board.thief_position
    snap = rules.compute_scent_field()
    assert snap[ty][tx] == pytest.approx(0.9, abs=0.01), (
        "Fresh snapshot must peak at current thief position"
    )
    accum = rules.get_scent_field()
    assert accum[ty][tx] == 0.0, "Accumulated scent must be zero before any moves"


# ---------------------------------------------------------------------------
# Config: max_turns from constructor, minimum enforced
# ---------------------------------------------------------------------------


def test_rules_engine_respects_max_turns_param():
    """When max_turns > 35 is negotiated, game should not end at 35."""
    board = Board(cop_position=[0, 0], thief_position=[6, 6])
    rules = RulesEngine(board, max_turns=50)
    assert rules.max_turns == 50
    board.turn = 35
    from cop_worker.rules_engine import GameOutcome

    assert rules.check_game_status() == GameOutcome.ONGOING, (
        "Game must not end at turn 35 when max_turns=50"
    )
    board.turn = 50
    assert rules.check_game_status() == GameOutcome.THIEF_WIN


def test_rules_engine_enforces_minimum_35_turns():
    """Even if caller passes max_turns < 35, engine must use at least 35."""
    board = Board(cop_position=[0, 0], thief_position=[6, 6])
    rules = RulesEngine(board, max_turns=5)
    assert rules.max_turns == 35, "max_turns must be clamped to minimum 35"
