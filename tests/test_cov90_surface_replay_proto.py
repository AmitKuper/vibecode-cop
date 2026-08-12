"""Coverage of the replay viewer, reference-v3 negotiation, and gamelet registry."""

from __future__ import annotations

import pytest


def test_replay_viewer_and_types(tmp_path):
    import json

    from cop_worker.replay.replay_app import ReplayError, ReplayState, ReplayViewer

    log = tmp_path / "g.json"
    log.write_text(
        json.dumps({"game_uid": "g", "steps": [{"step": 1}, {"step": 2}]}), encoding="utf-8"
    )
    viewer = ReplayViewer(log)
    first = viewer.current_state()
    assert viewer.is_at_start()
    viewer.step_forward()
    assert not viewer.is_at_start()
    viewer.step_backward()
    assert viewer.current_state() == first
    assert ReplayState(
        game_uid="u",
        gamelet=1,
        step=0,
        total_steps=2,
        event=None,
        verified=True,
        tamper_reason="",
        transcript_verified=True,
    ).verified
    with pytest.raises(ReplayError):
        raise ReplayError("x")


def test_replay_app_read_json_and_load_rejects(tmp_path):
    import json

    from cop_worker.replay.replay_app import ReplayApp, ReplayError

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(ReplayError, match="JSON object"):
        ReplayApp._read_json(str(bad))
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"a": 1}), encoding="utf-8")
    assert ReplayApp._read_json(str(good)) == {"a": 1}
    app = ReplayApp()
    with pytest.raises((ReplayError, FileNotFoundError, KeyError, TypeError)):
        app.load(str(tmp_path / "missing.json"), {})


def test_reference_v3_negotiation_roundtrip_and_reject():
    from cop_worker.protocol.reference_v3 import (
        NegotiatedReferenceV3,
        ReferenceV3Error,
        build_negotiation,
        default_terms,
        verify_negotiation,
    )

    ours = build_negotiation(
        terms=default_terms(),
        nonce="n" * 32,
        group_id="vibecode",
        group_name="ViBe",
        role="police",
        sub_game_number=1,
    )
    theirs = build_negotiation(
        terms=default_terms(),
        nonce="m" * 32,
        group_id="peer",
        group_name="Peer",
        role="thief",
        sub_game_number=1,
    )
    agreed = verify_negotiation(ours, theirs)
    assert isinstance(agreed, NegotiatedReferenceV3)
    with pytest.raises(ReferenceV3Error):
        verify_negotiation(ours, {"no": "terms"})


def test_mcp_server_gamelet_registry_lifecycle():
    import cop_worker.mcp_server as srv

    srv.clear_all_gamelets()
    terms = {
        "board_size": 7,
        "smell_grid_size": 5,
        "decay_per_step": 0.1,
        "emit_intensity": 0.9,
        "max_steps": 35,
        "survival_threshold": 35,
        "barriers_max": 14,
        "num_games": 6,
    }
    created = srv.start_gamelet("uid-cov", 1, terms, "peer", "police")
    assert created["ok"]
    from cop_worker.gamelet import GameletError

    with pytest.raises(GameletError, match="already exists"):
        srv.start_gamelet("uid-cov", 1, terms, "peer", "police")
    status = srv.get_status("uid-cov", 1)
    assert status["game_uid"] == "uid-cov" and status["role"] == "police"
    with pytest.raises(GameletError):
        srv.get_status("uid-cov", 9)
    down = srv.shutdown_gamelet("uid-cov", 1)
    assert down["ok"]
    srv.clear_all_gamelets()
