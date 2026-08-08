"""Fast unit tests for canonical shared-config load/validate/hash.

Reads the real cop/config.toml (no network) and exercises the validator with
in-memory dicts.
"""

from __future__ import annotations

import pytest

from cop_worker.config import shared_config as sc


def _valid_cfg() -> dict:
    return {
        "board_and_agents": {"grid_size": 7},
        "movement_and_barriers": {"max_barriers": 14, "max_moves": 35, "survival_threshold": 35},
        "scoring": {
            "technical_loss": 0, "capture_cop": 20, "capture_thief": 5,
            "survival_cop": 5, "survival_thief": 10, "tie_score": 2, "diversity_reward": 10,
        },
        "pheromones": {
            "pheromone_center_intensity": 0.9, "pheromone_decay": 0.10, "pheromone_grid_size": 5,
        },
        "network_and_league": {},
    }


def test_canonical_json_is_sorted_and_compact():
    assert sc.canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_config_sha256_is_stable_hex():
    h = sc.config_sha256({"a": 1})
    assert len(h) == 64 and h == sc.config_sha256({"a": 1})


def test_validate_accepts_a_valid_config():
    sc._validate(_valid_cfg())  # must not raise


def test_validate_rejects_missing_section():
    cfg = _valid_cfg()
    del cfg["scoring"]
    with pytest.raises(ValueError, match="missing required section"):
        sc._validate(cfg)


def test_validate_rejects_fixed_value_mismatch():
    cfg = _valid_cfg()
    cfg["scoring"]["capture_cop"] = 99
    with pytest.raises(ValueError, match="Fixed value mismatch"):
        sc._validate(cfg)


def test_validate_rejects_below_minimum():
    cfg = _valid_cfg()
    cfg["board_and_agents"]["grid_size"] = 5
    with pytest.raises(ValueError, match="Minimum value violated"):
        sc._validate(cfg)


def test_validate_rejects_reports_in_game_section():
    cfg = _valid_cfg()
    cfg["reports"] = {"mode": "dry_run"}
    with pytest.raises(ValueError, match="private section"):
        sc._validate(cfg)


def test_load_and_hash_real_config():
    cfg = sc.load_shared_config()  # auto-detects cop/config.toml
    assert sc._REQUIRED_SECTIONS.issubset(cfg.keys())
    assert len(sc.get_config_sha256()) == 64


def test_load_rejects_toml_without_game_sections(tmp_path):
    bad = tmp_path / "config.toml"
    bad.write_text("[other]\nx = 1\n")
    with pytest.raises(ValueError, match="No \\[game"):
        sc.load_shared_config(bad)


def test_resolve_path_raises_when_none_found(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "_SEARCH_PATHS", [tmp_path / "nope.toml"])
    with pytest.raises(FileNotFoundError):
        sc._resolve_path(None)
