"""Production CLI construction and dispatch coverage."""

from __future__ import annotations

from argparse import Namespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent.role_cli import (
    _assert_counted_worktree_clean,
    _model_record,
    _model_sha,
    _normalise_legacy,
    _resolved,
    _run,
    run_role_cli,
)

from agent.runtime_mode import RuntimeMode


def _args(config, tmp_path, **overrides):
    values = {
        "command": "serve",
        "mode": "counted",
        "config": str(config),
        "host": "0.0.0.0",
        "port": 61234,
        "peer_url": "http://peer.example/mcp",
        "secret": "production-test-secret",
        "games_dir": str(tmp_path / "games"),
        "n_gamelets": 6,
        "acceptance_fake_gmail_outbox": str(tmp_path / "fake.jsonl"),
    }
    values.update(overrides)
    return Namespace(**values)


def test_legacy_cli_normalization_and_manifest_missing(tmp_path):
    assert _normalise_legacy(["custom.toml", "--port", "1"]) == [
        "serve",
        "--config",
        "custom.toml",
        "--port",
        "1",
    ]
    assert _normalise_legacy(["series"]) == ["series"]
    missing = tmp_path / "missing.json"
    assert _model_sha("cop", missing) == "placeholder"
    assert _model_record("cop", missing) == {}


def test_resolved_builds_counted_process_dependencies(tmp_path):
    config = tmp_path / "cop.toml"
    config.write_text(
        """
[cop]
local_port = 5000
mcp_url = "http://old.example/mcp"
[crypto]
shared_secret = "private-secret"
[llm]
provider = "fixture"
model = "fixture-model"
""",
        encoding="utf-8",
    )
    with patch("agent.role_cli._detect_public_ip", return_value=""):
        runtime, orchestrator = _resolved("cop", _args(config, tmp_path))

    assert runtime["my_endpoint"] == "http://127.0.0.1:61234/mcp"
    assert runtime["opponent_url"] == "http://peer.example/mcp"
    assert runtime["secret"] == "production-test-secret"
    assert orchestrator["role"] == "cop"
    assert orchestrator["gmail_sender"].__class__.__name__ == "AcceptanceFileGmailSender"
    assert len(orchestrator["config_sha256"]) == 64


def test_resolved_constructs_real_gmail_sender_without_sending(tmp_path):
    config = tmp_path / "cop.toml"
    config.write_text(
        """
[cop]
peer_url = "http://peer.example/mcp"
[reports.gmail]
mode = "send"
token_path = "secrets/fixture-token.json"
""",
        encoding="utf-8",
    )
    args = _args(
        config,
        tmp_path,
        port=None,
        acceptance_fake_gmail_outbox=None,
        secret="",
    )
    _, orchestrator = _resolved("cop", args)
    assert orchestrator["gmail_sender"].__class__.__name__ == "GmailApiSender"


@pytest.mark.asyncio
async def test_run_dispatches_counted_series_and_rejects_thief_initiator(tmp_path):
    args = _args(tmp_path / "unused.toml", tmp_path, command="series")
    runtime = {
        "opponent_url": "http://peer/mcp",
        "secret": "secret",
        "config_sha256": "c" * 64,
        "games_dir": tmp_path,
        "group_name": "fixture",
        "llm_dict": None,
    }
    run_series = AsyncMock(return_value={"series_id": "fixture"})
    with (
        patch("agent.role_cli._assert_counted_worktree_clean"),
        patch("agent.role_cli._resolved", return_value=(runtime, {"role": "cop"})),
        patch("scripts.run_series.run_series", new=run_series),
    ):
        assert await _run("cop", args) == 0
    assert run_series.await_args.kwargs["mode"] is RuntimeMode.COUNTED

    with (
        patch("agent.role_cli._assert_counted_worktree_clean"),
        patch("agent.role_cli._resolved", return_value=(runtime, {})),
        pytest.raises(ValueError, match="Only the cop"),
    ):
        await _run("thief", args)


@pytest.mark.asyncio
async def test_run_dispatches_server_with_configured_and_default_ports(tmp_path):
    config = tmp_path / "thief.toml"
    config.write_text("[thief]\nlocal_port = 5432\n", encoding="utf-8")
    runtime = {
        "role": "thief",
        "secret": "secret",
        "config_sha256": "c" * 64,
        "opponent_url": "http://peer/mcp",
        "games_dir": tmp_path,
    }
    instance = MagicMock()
    instance.run_async = AsyncMock()
    with (
        patch("agent.role_cli._assert_counted_worktree_clean"),
        patch("agent.role_cli._resolved", return_value=(runtime, {})),
        patch("agent.peer_agent_runtime.PeerAgentRuntime", return_value=instance),
    ):
        assert await _run("thief", _args(config, tmp_path, port=None)) == 0
    instance.run_async.assert_awaited_once_with(host="0.0.0.0", port=5432)


def test_run_role_cli_parses_and_executes(tmp_path):
    async def fake_run(role, args):
        assert role == "cop"
        assert args.command == "serve"
        assert args.mode == "development"
        return 7

    with patch("agent.role_cli._run", new=fake_run):
        assert run_role_cli("cop", ["serve", "--games-dir", str(tmp_path)]) == 7


def test_counted_cli_rejects_dirty_or_unverifiable_git_provenance():
    with patch("subprocess.check_output", return_value=""):
        _assert_counted_worktree_clean()
    with (
        patch("subprocess.check_output", return_value=" M agent/role_cli.py\n?? model.pt\n"),
        pytest.raises(RuntimeError, match="worktree is dirty"),
    ):
        _assert_counted_worktree_clean()
    with (
        patch("subprocess.check_output", side_effect=OSError("git missing")),
        pytest.raises(RuntimeError, match="unable to verify"),
    ):
        _assert_counted_worktree_clean()
