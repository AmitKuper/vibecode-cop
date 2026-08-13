"""Cover config_loader profile resolution and mcp.log_replay utilities."""

from __future__ import annotations

import json

from cop_worker import config_loader
from cop_worker.mcp import log_replay


def test_resolve_profile_dir_variants(tmp_path):
    # No value -> base config dir.
    assert config_loader.resolve_profile_dir(None) == config_loader.CONFIG_DIR
    # An explicit existing directory path is returned verbatim.
    assert config_loader.resolve_profile_dir(str(tmp_path)) == tmp_path
    # A known opponent name resolves under config/opponents/.
    resolved = config_loader.resolve_profile_dir("anrbj666")
    assert resolved == config_loader.CONFIG_DIR / "opponents" / "anrbj666"
    # An unknown bare name falls back to the base config dir.
    assert config_loader.resolve_profile_dir("no_such_opp") == config_loader.CONFIG_DIR


def test_load_game_and_runtime_base():
    game = config_loader.load_game()
    runtime = config_loader.load_runtime()
    assert isinstance(game, dict) and game
    assert isinstance(runtime, dict) and runtime


def test_load_from_file_reads_jsonl_and_handles_missing(tmp_path):
    log = tmp_path / "events.jsonl"
    log.write_text('{"a": 1}\n\n{"b": 2}\n', encoding="utf-8")
    events = log_replay.load_from_file(log)
    assert events == [{"a": 1}, {"b": 2}]
    # A missing file is logged and yields an empty list, not an exception.
    assert log_replay.load_from_file(tmp_path / "missing.jsonl") == []


def test_load_log_json_and_hashers(tmp_path):
    data = {"game_id": "G", "entries": []}
    path = tmp_path / "log.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert log_replay.load_log_json(path) == data
    assert log_replay.canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    assert len(log_replay.sha256_of_json(data)) == 64
    assert log_replay.sha256_of_file(path) == log_replay.sha256_of_file(path)


def test_audit_log_commitments_gamelet_parse_fallback():
    # A non-numeric game_number falls back to gamelet 1 without raising.
    result = log_replay.audit_log_commitments({"game_number": "gxx", "entries": []})
    assert result["verified"] == 0 and result["ok"] is False
