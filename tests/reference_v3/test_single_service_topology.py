"""Test single-service topology where one URL handles both roles."""

from league_manager.peer_topology import PeerTopology


def test_our_single_address_deployment_works():
    """Single-service topology must route both roles to one URL.

    Note: PeerTopology uses 'police' (not 'cop') as the role key.
    """
    topo = PeerTopology(mode="single", single_url="http://localhost:8000")
    assert topo.get_url_for_role("police") == "http://localhost:8000"
    assert topo.get_url_for_role("thief") == "http://localhost:8000"
