"""Test receive_turn payload shape matches ref-v3 schema."""

from cop_worker.observation_processor import ObservationProcessor


def test_receive_turn_payload_matches_ref_v3_schema():
    """ObservationProcessor must normalise a valid opponent_turn payload."""
    proc = ObservationProcessor()
    payload = {
        "step": 1,
        "kind": "commit",
        "commitment_hash": "a" * 64,
        "nonce": None,
        "action": None,
    }
    turn = proc.normalise_turn(payload)
    assert turn.step == 1
    assert turn.kind == "commit"
    assert turn.commitment_hash == "a" * 64
