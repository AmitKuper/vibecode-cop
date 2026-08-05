"""Red/green tests for the real fail-closed counted composition root."""

from __future__ import annotations

import json
from hashlib import sha256
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import torch

from agent.runtime_mode import RuntimeMode


def _manifest(tmp_path):
    from agent.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
    from agent.rl.local_obs_adapter import obs_tensor_shape
    from agent.rl.recurrent_policy import RecurrentActorCritic

    tmp_path.mkdir(parents=True, exist_ok=True)
    entries = []
    torch.manual_seed(17)
    for role, actions in (("cop", COP_ACTIONS), ("thief", THIEF_ACTIONS)):
        network = RecurrentActorCritic(obs_tensor_shape(7), len(actions), hidden_size=8)
        artifact = tmp_path / f"{role}_fixture.pt"
        torch.save(
            {
                "role": role,
                "algorithm": "RecurrentA2C-GRU",
                "input_size": obs_tensor_shape(7),
                "n_actions": len(actions),
                "hidden_size": 8,
                "training_steps": 35,
                "state_dict": network.state_dict(),
            },
            artifact,
        )
        entries.append(
            {
                "role": role,
                "algorithm": "RecurrentA2C-GRU",
                "artifact": artifact.name,
                "architecture": "encoder-tanh-grucell-policy-value",
                "sha256": sha256(artifact.read_bytes()).hexdigest(),
                "training_code_sha": "b" * 40,
                "config_sha256": "c" * 64,
                "observation_schema_version": "1.0",
                "action_schema_version": "1.0",
                "belief_schema_version": "1.0",
                "inference_mode": "argmax",
                "grid_size": 7,
                "training_steps": 35,
                "evaluation_win_rate": 0.5,
            }
        )
    path = tmp_path / "MANIFEST.json"
    path.write_text(json.dumps({"models": entries}), encoding="utf-8")
    return path


def _counted_config(tmp_path, role="cop"):
    manifest_path = _manifest(tmp_path)
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))["models"]
    model_sha = next(item["sha256"] for item in entries if item["role"] == role)
    return {
        "secret": "unit-test-production-secret",
        "enforce_git_check": True,
        "model_sha256": model_sha,
        "model_manifest_path": str(manifest_path),
        "grid_size": 7,
        "role": role,
        "group_id": "ABCD1234",
        "canonical_config_sha256": "c" * 64,
        "config_sha256": "c" * 64,
        "scent_model_hash": "d" * 64,
        "gmail_sender": lambda *_args: "fake-test-message-id",
    }


def _runtime(tmp_path, **kwargs):
    from agent.peer_runtime import PeerRuntime

    role = kwargs.pop("role", "cop")
    return PeerRuntime(
        role=role,
        secret="unit-test-production-secret",
        config_sha256="c" * 64,
        opponent_url="http://127.0.0.1:65530/mcp",
        games_dir=tmp_path,
        counted_mode=True,
        orchestrator_config=kwargs.pop("orchestrator_config", _counted_config(tmp_path, role=role)),
        **kwargs,
    )


def test_complete_counted_orchestrator_passes_real_git_precondition(tmp_path):
    from agent.agent_orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator(
        role="cop",
        game_uid="series_fixture_g01",
        grid_size=7,
        mode=RuntimeMode.COUNTED,
        work_dir=str(tmp_path),
        config=_counted_config(tmp_path),
    )
    assert orchestrator.mode is RuntimeMode.COUNTED


def test_peer_runtime_builds_counted_orchestrator_with_complete_config(tmp_path):
    runtime = _runtime(tmp_path)
    captured = {}

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    with patch("agent.agent_orchestrator.AgentOrchestrator", FakeOrchestrator):
        runtime._ensure_orchestrator("series_fixture_g01")

    assert captured["mode"] is RuntimeMode.COUNTED
    assert captured["config"]["secret"] == "unit-test-production-secret"


def test_counted_orchestrator_construction_failure_is_not_swallowed(tmp_path):
    runtime = _runtime(tmp_path)

    class BrokenOrchestrator:
        def __init__(self, **kwargs):
            raise ValueError("counted dependency missing")

    with (
        patch("agent.agent_orchestrator.AgentOrchestrator", BrokenOrchestrator),
        pytest.raises(RuntimeError, match="AgentOrchestrator"),
    ):
        runtime._ensure_orchestrator("series_fixture_g01")


@pytest.mark.asyncio
async def test_counted_adaptive_negotiation_failure_is_not_identity_fallback(tmp_path):
    runtime = _runtime(tmp_path)
    with (
        patch(
            "agent.adaptive.pipeline.run_adaptive_negotiation",
            new=AsyncMock(side_effect=RuntimeError("incompatible peer")),
        ),
        pytest.raises(RuntimeError, match="Adaptive negotiation"),
    ):
        await runtime._init_protocol_adapter()
    assert runtime.protocol_adapter is None


@pytest.mark.asyncio
async def test_counted_series_locks_one_adaptive_profile_for_all_gamelets(tmp_path):
    from agent.adaptive.pipeline import native_adapter

    runtime = _runtime(tmp_path)
    negotiation = AsyncMock(return_value=native_adapter())
    with patch("agent.adaptive.pipeline.run_adaptive_negotiation", new=negotiation):
        await runtime._init_protocol_adapter()
        profile_hash = runtime._adaptive_profile.profile_hash
        await runtime._init_protocol_adapter()

    assert negotiation.await_count == 1
    assert runtime._adaptive_profile.profile_hash == profile_hash


@pytest.mark.asyncio
async def test_counted_series_propagates_gamelet_failure(tmp_path):
    from scripts.run_series import run_series

    fake_proc = MagicMock()
    fake_proc.stdout = "d" * 40
    with (
        patch("subprocess.check_output", return_value=fake_proc),
        patch("agent.peer_runtime.PeerRuntime.run_game", side_effect=RuntimeError("peer abort")),
        pytest.raises(RuntimeError, match="peer abort"),
    ):
        await run_series(
            thief_url="http://127.0.0.1:65530/mcp",
            secret="unit-test-production-secret",
            config_sha256="c" * 64,
            games_dir=tmp_path,
            n_gamelets=6,
            group_name="fixture",
            mode=RuntimeMode.COUNTED,
            orchestrator_config=_counted_config(tmp_path),
        )


def test_counted_peer_agent_passes_mode_to_passive_runtime(tmp_path):
    from agent.peer_agent_runtime import PeerAgentRuntime

    with (
        patch("agent.peer_agent_runtime.PeerRuntime") as runtime_cls,
        patch("agent.peer_agent_runtime.AgentMCPServer"),
    ):
        runtime_cls.return_value.llm = None
        PeerAgentRuntime(
            role="thief",
            secret="unit-test-production-secret",
            config_sha256="c" * 64,
            opponent_url="http://127.0.0.1:65530/mcp",
            games_dir=tmp_path,
            mode=RuntimeMode.COUNTED,
            orchestrator_config=_counted_config(tmp_path, role="thief"),
        )
    assert runtime_cls.call_args.kwargs["counted_mode"] is True
    assert runtime_cls.call_args.kwargs["orchestrator_config"]["role"] == "thief"


def test_counted_step0_is_bilateral_signed_and_identity_bound(tmp_path):
    from agent.adaptive.pipeline import native_adapter
    from agent.peer_step0 import (
        Step0ExchangeError,
        accept_remote_signed_declaration,
        build_local_signed_declaration,
    )

    cop = _runtime(tmp_path / "cop", role="cop")
    thief = _runtime(tmp_path / "thief", role="thief")
    game_id = "series_fixture_g01"
    for runtime in (cop, thief):
        runtime._ensure_orchestrator(game_id)
        runtime._adaptive_profile = native_adapter().profile
    cop_signed = build_local_signed_declaration(cop, game_id)
    thief_signed = build_local_signed_declaration(thief, game_id)
    cop_agreement = accept_remote_signed_declaration(cop, game_id, thief_signed.to_dict())
    thief_agreement = accept_remote_signed_declaration(thief, game_id, cop_signed.to_dict())

    assert cop_agreement.agreement_hash == thief_agreement.agreement_hash
    assert cop._remote_step0[game_id].declaration.public_key_hex == (
        thief._signing_public_key.hex()
    )

    tampered = thief_signed.to_dict()
    tampered["declaration"]["config_sha256"] = "e" * 64
    with pytest.raises(Step0ExchangeError, match="signature"):
        accept_remote_signed_declaration(cop, game_id, tampered)
