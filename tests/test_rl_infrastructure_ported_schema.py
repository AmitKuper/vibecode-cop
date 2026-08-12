"""Tests for Phase 4: RL infrastructure — model schema, file validation, manifest."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile

import pytest

from cop_worker.rl.model_schema import (
    CURRENT_ACTION_SCHEMA_VERSION,
    CURRENT_OBSERVATION_SCHEMA_VERSION,
    ModelLoadError,
    ModelManifestEntry,
    load_manifest,
    validate_model_file,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_entry(**overrides) -> ModelManifestEntry:
    defaults = {
        "role": "cop",
        "algorithm": "PPO",
        "sha256": "abc",
        "training_code_sha": "placeholder",
        "config_sha256": "placeholder",
        "observation_schema_version": CURRENT_OBSERVATION_SCHEMA_VERSION,
        "action_schema_version": CURRENT_ACTION_SCHEMA_VERSION,
        "belief_schema_version": "1.0",
        "inference_mode": "argmax",
        "grid_size": 7,
    }
    defaults.update(overrides)
    return ModelManifestEntry(**defaults)


# ---------------------------------------------------------------------------
# Model schema tests
# ---------------------------------------------------------------------------


class TestModelManifestEntry:
    def test_compatible_same_role_and_grid(self):
        entry = _make_entry()
        ok, reason = entry.is_compatible("cop", 7)
        assert ok
        assert reason == ""

    def test_role_mismatch(self):
        entry = _make_entry(role="cop")
        ok, reason = entry.is_compatible("thief", 7)
        assert not ok
        assert "role" in reason

    def test_grid_size_mismatch(self):
        entry = _make_entry(grid_size=5)
        ok, reason = entry.is_compatible("cop", 7)
        assert not ok
        assert "grid_size" in reason

    def test_obs_schema_version_mismatch(self):
        entry = _make_entry(observation_schema_version="0.9")
        ok, reason = entry.is_compatible("cop", 7)
        assert not ok
        assert "obs schema" in reason

    def test_action_schema_version_mismatch(self):
        entry = _make_entry(action_schema_version="0.9")
        ok, reason = entry.is_compatible("cop", 7)
        assert not ok
        assert "action schema" in reason


class TestValidateModelFile:
    def test_correct_hash_passes(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            path = f.name
        try:
            h = hashlib.sha256(b"test content").hexdigest()
            validate_model_file(path, h)  # should not raise
        finally:
            os.unlink(path)

    def test_wrong_hash_raises(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            path = f.name
        try:
            with pytest.raises(ModelLoadError, match="hash mismatch"):
                validate_model_file(path, "deadbeef" * 8)
        finally:
            os.unlink(path)


class TestLoadManifest:
    def test_load_valid_manifest(self):
        manifest_data = {
            "manifest_version": "1.0",
            "models": [
                {
                    "role": "cop",
                    "algorithm": "PPO",
                    "sha256": "abc123",
                    "training_code_sha": "placeholder",
                    "config_sha256": "placeholder",
                    "observation_schema_version": "1.0",
                    "action_schema_version": "1.0",
                    "belief_schema_version": "1.0",
                    "inference_mode": "argmax",
                    "grid_size": 7,
                }
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            path = f.name
        try:
            result = load_manifest(path)
            assert "cop" in result
            assert result["cop"].algorithm == "PPO"
            assert result["cop"].grid_size == 7
        finally:
            os.unlink(path)
