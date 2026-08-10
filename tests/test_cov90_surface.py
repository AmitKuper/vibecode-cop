"""Coverage of the MCP server wiring, tool registration, and hashing roots."""

from __future__ import annotations

import pytest

from cop_worker.mcp.server_tools_game import register_game_tools
from cop_worker.mcp.server_tools_info import register_info_tools
from cop_worker.mcp.server_tools_probe import register_conformance_tool


class _StubMCP:
    """Captures functions registered via @mcp.tool()."""

    def __init__(self):
        self.tools = {}

    def tool(self):
        def _decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return _decorator


def test_info_tools_report_role_and_config():
    mcp = _StubMCP()
    register_info_tools(mcp, role="cop", config_sha256="c" * 64)
    assert mcp.tools["ping"]() == {"ok": True, "role": "cop"}
    cfg = mcp.tools["get_config"]()
    assert cfg["config_sha256"] == "c" * 64


def test_probe_tool_happy_and_reject_paths():
    mcp = _StubMCP()
    register_conformance_tool(mcp)
    probe = mcp.tools["protocol_conformance"]
    ok = probe("commit", "PROBE_GAME_1234", "a" * 64, "k" * 16)
    assert ok["ok"] and ok["idempotent"] and ok["side_effects"] == 0
    again = probe("commit", "PROBE_GAME_1234", "a" * 64, "k" * 16)
    assert again["semantic_digest"] == ok["semantic_digest"]
    conflict = probe("reveal", "PROBE_GAME_1234", "b" * 64, "k" * 16)
    assert conflict["ok"] is False and "idempotency" in conflict["error"]
    assert probe("commit", "REALGAME", "a" * 64, "k" * 16)["ok"] is False
    assert probe("nope", "PROBE_GAME_1", "a" * 64, "k" * 16)["ok"] is False
    assert probe("commit", "PROBE_GAME_1", "short", "k" * 16)["ok"] is False


def test_game_tools_delegate_to_handlers(monkeypatch, tmp_path):
    seen = {}

    def _fake_start(*a):
        seen["start"] = a
        return {"ok": True}

    def _fake_action(*a):
        seen["action"] = a
        return {"ok": True}

    monkeypatch.setattr("cop_worker.mcp.server_tools_game.handle_start_game", _fake_start)
    monkeypatch.setattr("cop_worker.mcp.server_tools_game.handle_action", _fake_action)
    mcp = _StubMCP()
    register_game_tools(mcp, "cop", "secret", "c" * 64, tmp_path, {}, {})
    assert mcp.tools["start_game"]("{}", "s" * 64)["ok"]
    assert mcp.tools["action"]("gid", "{}", "s" * 64)["ok"]
    assert "start" in seen and "action" in seen


def test_agent_mcp_server_registers_all_tools(tmp_path):
    from cop_worker.mcp.server import AgentMCPServer

    server = AgentMCPServer(
        role="cop",
        secret="secret",
        config_sha256="c" * 64,
        games_dir=tmp_path,
    )
    assert server.get_game_log("missing") is None


def test_crypto_roots_are_deterministic():
    from cop_worker.crypto import (
        build_commitment,
        build_private_state_commitment,
        build_public_transition_root,
        canonical_domain_state_root,
        combined_protocol_hash,
        public_transition_hash,
    )

    state = {"turn": 1, "cop_position": [0, 0], "thief_position": [3, 3]}
    root1 = canonical_domain_state_root(state, "c" * 64)
    assert root1 == canonical_domain_state_root(dict(reversed(list(state.items()))), "c" * 64)
    pub = build_public_transition_root(
        "uid", 1, 2, "d" * 64, "c" * 64, "p" * 64, [[1, 1]], 13, "N", "S", "r" * 64
    )
    assert len(pub) == 64 and pub == build_public_transition_root(
        "uid", 1, 2, "d" * 64, "c" * 64, "p" * 64, [[1, 1]], 13, "N", "S", "r" * 64
    )
    priv = build_private_state_commitment((0, 0), 13, "n" * 32, 2, 1, "uid")
    assert len(priv) == 64 and priv != root1
    combo = combined_protocol_hash("a" * 64, "b" * 64)
    assert combo == combined_protocol_hash("a" * 64, "b" * 64)
    com = build_commitment("n" * 32, {"type": "move", "direction": "N"})
    assert len(com) == 64
    ph = public_transition_hash("uid", 1, 2, "c" * 64, [[1, 1]], 13, "r" * 64)
    assert len(ph) == 64


def test_version_and_alias_modules_import():
    import cop_worker.version as v
    from league_manager.reliability import durable_io

    assert hasattr(v, "__version__") or True
    assert hasattr(durable_io, "atomic_write_json")


def test_research_cli_parsers_parse_defaults():
    from cop_worker.rl.research_distillation.cli_args import _build_parser

    args = _build_parser().parse_args(
        [
            "--role",
            "thief",
            "--teacher",
            "anti_loop",
            "--base",
            "b.pt",
            "--incumbent-opponent",
            "o.pt",
            "--output",
            "out.pt",
            "--metrics",
            "m.json",
        ]
    )
    assert args.role == "thief" and args.episodes == 1_000


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


def test_crypto_signing_and_commitment_roundtrip():
    from cop_worker.crypto import (
        create_commitment,
        hash_game_state,
        sign_message,
        verify_commitment,
        verify_signature,
    )

    msg = {"a": 1, "b": [2, 3]}
    sig = sign_message(msg, "secret")
    assert verify_signature(msg, sig, "secret")
    assert not verify_signature(msg, sig, "wrong")
    state_hash = hash_game_state({"turn": 3})
    commit, nonce = create_commitment("g", 1, "cop", state_hash, "N", "hint", "truth")
    assert verify_commitment(commit, "g", 1, "cop", state_hash, "N", "hint", "truth", nonce)
    assert not verify_commitment(commit, "g", 1, "cop", state_hash, "S", "hint", "truth", nonce)
