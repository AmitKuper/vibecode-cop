"""Tests for counted-mode model validation (Phase 4 v7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.agent_orchestrator import AgentOrchestrator
from agent.runtime_mode import RuntimeMode


def _make_manifest(
    tmp_path: Path, training_steps: int = 0, win_rate: float = 0.0, role: str = "thief"
) -> str:
    """Write a minimal MANIFEST.json to tmp_path and return its path string."""
    manifest = {
        "manifest_version": "1.0",
        "models": [
            {
                "role": role,
                "algorithm": "PPO",
                "sha256": "abc123",
                "training_code_sha": "placeholder",
                "config_sha256": "placeholder",
                "observation_schema_version": "1.0",
                "action_schema_version": "1.0",
                "belief_schema_version": "1.0",
                "inference_mode": "argmax",
                "grid_size": 7,
                "random_seed": 42,
                "training_steps": training_steps,
                "hyperparams": {},
                "evaluation_win_rate": win_rate,
                "description": "test model",
            }
        ],
    }
    path = tmp_path / "MANIFEST.json"
    path.write_text(json.dumps(manifest))
    return str(path)


def _counted_config(manifest_path: str, role: str = "thief") -> dict:
    return {
        "secret": "real-production-secret-xyz",
        "model_sha256": "abc123deadbeef",
        "model_manifest_path": manifest_path,
        "grid_size": 7,
    }


def test_counted_mode_rejects_missing_manifest(tmp_path):
    config = _counted_config(str(tmp_path / "nonexistent.json"))
    with pytest.raises(ValueError, match="manifest not found"):
        AgentOrchestrator(
            role="thief",
            game_uid="test-missing",
            grid_size=7,
            mode=RuntimeMode.COUNTED,
            config=config,
        )


def test_counted_mode_rejects_zero_training_steps(tmp_path):
    manifest_path = _make_manifest(tmp_path, training_steps=0, win_rate=0.75)
    config = _counted_config(manifest_path)
    with pytest.raises(ValueError, match="training_steps=0"):
        AgentOrchestrator(
            role="thief",
            game_uid="test-zero-steps",
            grid_size=7,
            mode=RuntimeMode.COUNTED,
            config=config,
        )


def test_development_mode_skips_model_validation(tmp_path):
    # DEVELOPMENT mode should not check manifest at all
    orch = AgentOrchestrator(
        role="thief",
        game_uid="test-dev",
        grid_size=7,
        mode=RuntimeMode.DEVELOPMENT,
        config={},
    )
    assert orch.mode == RuntimeMode.DEVELOPMENT


def test_model_validated_on_orchestrator_init(tmp_path):
    """AgentOrchestrator in COUNTED mode with placeholder manifest raises ValueError."""
    # Use a temp manifest with training_steps=0 to test rejection logic
    manifest_path = _make_manifest(tmp_path, training_steps=0, win_rate=0.0)
    config = _counted_config(manifest_path)
    with pytest.raises(ValueError, match="COUNTED mode rejected"):
        AgentOrchestrator(
            role="thief",
            game_uid="test-placeholder",
            grid_size=7,
            mode=RuntimeMode.COUNTED,
            config=config,
        )
