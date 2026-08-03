"""Tests for lifecycle artifact path generation and validation."""

import json

from agent.step0.lifecycle_artifacts import (
    LifecycleArtifactSet,
    build_artifact_set,
    config_path,
    declaration_path,
    log_path,
    result_path,
)

GAME_UID = "abc-123-def-456"
BASE = "/tmp/artifacts"


# ---------------------------------------------------------------------------
# Path generation
# ---------------------------------------------------------------------------


def test_declaration_path_format():
    p = declaration_path(BASE, GAME_UID)
    assert p.endswith(f"declaration_{GAME_UID}.json")


def test_result_path_format():
    p = result_path(BASE, GAME_UID)
    assert p.endswith(f"result_{GAME_UID}.json")


def test_config_path_gamelet_zero_padded():
    p = config_path(BASE, GAME_UID, 1)
    assert "g01" in p
    p9 = config_path(BASE, GAME_UID, 9)
    assert "g09" in p9


def test_log_path_gamelet_zero_padded():
    p = log_path(BASE, GAME_UID, 6)
    assert "g06" in p


def test_config_path_double_digit_gamelet():
    p = config_path(BASE, GAME_UID, 10)
    assert "g10" in p


def test_log_path_double_digit_gamelet():
    p = log_path(BASE, GAME_UID, 12)
    assert "g12" in p


# ---------------------------------------------------------------------------
# Six-gamelet artifact set
# ---------------------------------------------------------------------------


def test_build_artifact_set_six_gamelets():
    arts = build_artifact_set(BASE, GAME_UID, num_gamelets=6)
    assert len(arts.config_paths) == 6
    assert len(arts.log_paths) == 6


def test_build_artifact_set_config_paths_correct():
    arts = build_artifact_set(BASE, GAME_UID, num_gamelets=6)
    for i, p in enumerate(arts.config_paths, start=1):
        assert f"g{i:02d}" in p
        assert GAME_UID in p


def test_build_artifact_set_log_paths_correct():
    arts = build_artifact_set(BASE, GAME_UID, num_gamelets=6)
    for i, p in enumerate(arts.log_paths, start=1):
        assert f"g{i:02d}" in p
        assert GAME_UID in p


def test_build_artifact_set_game_uid():
    arts = build_artifact_set(BASE, GAME_UID)
    assert arts.game_uid == GAME_UID


# ---------------------------------------------------------------------------
# validate_all_present
# ---------------------------------------------------------------------------


def test_validate_all_present_returns_missing(tmp_path):
    arts = build_artifact_set(str(tmp_path), GAME_UID, num_gamelets=2)
    missing = arts.validate_all_present()
    # All files are missing since we haven't created any
    total = 1 + 2 + 2 + 1  # declaration + configs + logs + result
    assert len(missing) == total


def test_validate_all_present_empty_when_all_exist(tmp_path):
    arts = build_artifact_set(str(tmp_path), GAME_UID, num_gamelets=2)
    # Create all the expected files
    for p in [arts.declaration_path] + arts.config_paths + arts.log_paths + [arts.result_path]:
        with open(p, "w") as f:
            json.dump({}, f)
    missing = arts.validate_all_present()
    assert missing == []


def test_validate_all_present_partial_missing(tmp_path):
    arts = build_artifact_set(str(tmp_path), GAME_UID, num_gamelets=2)
    # Create only the declaration file
    with open(arts.declaration_path, "w") as f:
        json.dump({}, f)
    missing = arts.validate_all_present()
    # All except declaration should be missing
    assert arts.declaration_path not in missing
    assert len(missing) == 5  # 2 configs + 2 logs + result


# ---------------------------------------------------------------------------
# LifecycleArtifactSet dataclass
# ---------------------------------------------------------------------------


def test_lifecycle_artifact_set_fields():
    arts = LifecycleArtifactSet(
        game_uid=GAME_UID,
        declaration_path="/tmp/decl.json",
        config_paths=["/tmp/cfg01.json"],
        log_paths=["/tmp/log01.json"],
        result_path="/tmp/result.json",
    )
    assert arts.game_uid == GAME_UID
    assert len(arts.config_paths) == 1
    assert len(arts.log_paths) == 1
