"""Tests for PeerTopology — URL resolution for cop and thief roles."""

import pytest

from league_manager.peer_topology import PeerTopology


def test_single_mode_returns_single_url():
    """Single topology must return single_url for any role."""
    topo = PeerTopology.single("http://peer:8080")
    assert topo.get_url_for_role("police") == "http://peer:8080"
    assert topo.get_url_for_role("thief") == "http://peer:8080"


def test_role_split_returns_cop_url_for_police():
    """Role-split topology must return cop_url for 'police'."""
    topo = PeerTopology.role_split("http://cop:8080", "http://thief:9090")
    assert topo.get_url_for_role("police") == "http://cop:8080"


def test_role_split_returns_thief_url_for_thief():
    """Role-split topology must return thief_url for 'thief'."""
    topo = PeerTopology.role_split("http://cop:8080", "http://thief:9090")
    assert topo.get_url_for_role("thief") == "http://thief:9090"


def test_single_mode_missing_url_raises():
    """single_url=None in single mode must raise ValueError."""
    topo = PeerTopology(mode="single", single_url=None)
    with pytest.raises(ValueError):
        topo.get_url_for_role("police")


def test_unknown_mode_raises():
    """Unknown mode must raise ValueError."""
    topo = PeerTopology(mode="unknown")  # type: ignore[arg-type]
    with pytest.raises((ValueError, Exception)):
        topo.get_url_for_role("police")


def test_role_split_missing_cop_url_raises():
    """role_split with cop_url=None for 'police' must raise ValueError."""
    topo = PeerTopology(mode="role_split", thief_url="http://thief:9090")
    with pytest.raises(ValueError):
        topo.get_url_for_role("police")
