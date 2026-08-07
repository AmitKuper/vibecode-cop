"""Tests for canonical shared config loading and compliance."""

import hashlib
import json
from pathlib import Path

import pytest

from cop_worker.config.shared_config import (
    _validate,
    canonical_json,
    config_sha256,
    load_shared_config,
)

_VALID_CONFIG = {
    "board_and_agents": {"grid_size": 7},
    "movement_and_barriers": {
        "max_barriers": 14,
        "max_moves": 35,
        "survival_threshold": 35,
    },
    "scoring": {
        "capture_cop": 20,
        "capture_thief": 5,
        "survival_cop": 5,
        "survival_thief": 10,
        "tie_score": 2,
        "technical_loss": 0,
        "diversity_reward": 10,
    },
    "pheromones": {
        "pheromone_center_intensity": 0.9,
        "pheromone_decay": 0.10,
        "pheromone_grid_size": 5,
    },
    "network_and_league": {},
}


def _write_config(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


class TestCanonicalJson:
    def test_sorted_keys(self):
        obj = {"b": 2, "a": 1}
        result = canonical_json(obj)
        assert result.index('"a"') < result.index('"b"')

    def test_no_extra_whitespace(self):
        result = canonical_json({"k": "v"})
        assert " " not in result

    def test_deterministic(self):
        obj = {"z": 3, "a": 1, "m": 2}
        assert canonical_json(obj) == canonical_json(obj)


class TestConfigSha256:
    def test_returns_64_hex_chars(self):
        sha = config_sha256({"x": 1})
        assert len(sha) == 64
        assert all(c in "0123456789abcdef" for c in sha)

    def test_different_configs_differ(self):
        assert config_sha256({"a": 1}) != config_sha256({"a": 2})

    def test_matches_manual_sha256(self):
        cfg = {"key": "value"}
        expected = hashlib.sha256(canonical_json(cfg).encode("utf-8")).hexdigest()
        assert config_sha256(cfg) == expected


class TestValidate:
    def test_valid_config_passes(self):
        _validate(_VALID_CONFIG)  # should not raise

    def test_missing_section_raises(self):
        cfg = dict(_VALID_CONFIG)
        del cfg["scoring"]
        with pytest.raises(ValueError, match="scoring"):
            _validate(cfg)

    def test_technical_loss_must_be_zero(self):
        cfg = json.loads(json.dumps(_VALID_CONFIG))
        cfg["scoring"]["technical_loss"] = 5
        with pytest.raises(ValueError, match="technical_loss"):
            _validate(cfg)

    def test_pheromone_center_intensity_fixed(self):
        cfg = json.loads(json.dumps(_VALID_CONFIG))
        cfg["pheromones"]["pheromone_center_intensity"] = 0.5
        with pytest.raises(ValueError, match="pheromone_center_intensity"):
            _validate(cfg)

    def test_max_barriers_minimum(self):
        cfg = json.loads(json.dumps(_VALID_CONFIG))
        cfg["movement_and_barriers"]["max_barriers"] = 10
        with pytest.raises(ValueError, match="max_barriers"):
            _validate(cfg)

    def test_max_moves_minimum(self):
        cfg = json.loads(json.dumps(_VALID_CONFIG))
        cfg["movement_and_barriers"]["max_moves"] = 20
        with pytest.raises(ValueError, match="max_moves"):
            _validate(cfg)

    def test_reports_section_forbidden(self):
        cfg = json.loads(json.dumps(_VALID_CONFIG))
        cfg["reports"] = {"gmail": {"mode": "send"}}
        with pytest.raises(ValueError, match="reports"):
            _validate(cfg)


class TestLoadSharedConfig:
    def test_loads_real_config(self):
        cfg = load_shared_config(Path("cop/config.toml"))
        assert "board_and_agents" in cfg
        assert "movement_and_barriers" in cfg

    def test_missing_file_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_shared_config(Path("config/nonexistent.toml"))

    def test_sha256_is_deterministic(self):
        sha1 = config_sha256(load_shared_config(Path("cop/config.toml")))
        sha2 = config_sha256(load_shared_config(Path("cop/config.toml")))
        assert sha1 == sha2

    def test_config_toml_passes_validation(self):
        cfg = load_shared_config(Path("cop/config.toml"))
        _validate(cfg)  # should not raise
