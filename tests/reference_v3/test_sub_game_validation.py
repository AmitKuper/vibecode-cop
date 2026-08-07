"""Test sub_game_number range validation."""

import pytest

from league_manager.router import Router, RouterError
from league_manager.tests.mock_worker import MockWorker


def make_router():
    """Create a Router with mock workers for testing."""
    cop = MockWorker(role="police")
    thief = MockWorker(role="thief")
    return Router(cop_worker=cop, thief_worker=thief)


def test_sub_game_number_out_of_range_rejected():
    """Router must raise RouterError when sub_game_number is 7 (out of range)."""
    r = make_router()
    r.register_series("game_sg_001")
    with pytest.raises(RouterError):
        r.route("game_sg_001", 7, "get_status", {})


def test_sub_game_number_zero_rejected():
    """Router must raise RouterError when sub_game_number is 0 (out of range)."""
    r = make_router()
    r.register_series("game_sg_002")
    with pytest.raises(RouterError):
        r.route("game_sg_002", 0, "get_status", {})
