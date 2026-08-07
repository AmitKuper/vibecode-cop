"""Test role-split topology where cop and thief use different URLs."""

from league_manager.peer_topology import PeerTopology


def test_role_split_peer_calls_handled_correctly():
    """Role-split topology must route each role to its own URL.

    Note: PeerTopology uses 'police' (not 'cop') as the role key,
    matching the canonical role name used throughout the system.
    """
    topo = PeerTopology(
        mode="role_split",
        cop_url="http://cop.example.com:8001",
        thief_url="http://thief.example.com:8002",
    )
    assert topo.get_url_for_role("police") == "http://cop.example.com:8001"
    assert topo.get_url_for_role("thief") == "http://thief.example.com:8002"
