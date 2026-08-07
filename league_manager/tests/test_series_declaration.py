"""Tests for series declaration writing."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from league_manager.step0.series_declaration import write_series_declaration


def test_writes_json_file(tmp_path):
    """write_series_declaration creates the expected JSON file."""
    with (
        patch("league_manager.step0.series_declaration.get_git_sha", return_value="abc123"),
        patch("league_manager.step0.series_declaration.is_git_clean", return_value=True),
    ):
        path = write_series_declaration(
            game_id="TEST001",
            game_uid="uid_001",
            group_id="vibecode",
            opponent_group="opponent",
            role="police",
            output_dir=tmp_path,
        )
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["game_id"] == "TEST001"
    assert data["role"] == "police"
    assert data["git_sha"] == "abc123"


def test_counted_dirty_repo_raises(tmp_path):
    """counted=True with a dirty repo raises RuntimeError."""
    with (
        patch("league_manager.step0.series_declaration.get_git_sha", return_value="abc"),
        patch("league_manager.step0.series_declaration.is_git_clean", return_value=False),
        pytest.raises(RuntimeError, match="clean git"),
    ):
        write_series_declaration(
            game_id="TEST002",
            game_uid="uid_002",
            group_id="vibecode",
            opponent_group="opponent",
            role="police",
            output_dir=tmp_path,
            counted=True,
        )


def test_friendly_run_allows_dirty_repo(tmp_path):
    """counted=False allows a dirty repo without raising."""
    with (
        patch("league_manager.step0.series_declaration.get_git_sha", return_value="abc"),
        patch("league_manager.step0.series_declaration.is_git_clean", return_value=False),
    ):
        path = write_series_declaration(
            game_id="TEST003",
            game_uid="uid_003",
            group_id="vibecode",
            opponent_group="opponent",
            role="thief",
            output_dir=tmp_path,
            counted=False,
        )
    assert path.exists()


def test_file_named_after_game_id(tmp_path):
    """Declaration file name includes the game_id."""
    with (
        patch("league_manager.step0.series_declaration.get_git_sha", return_value="sha99"),
        patch("league_manager.step0.series_declaration.is_git_clean", return_value=True),
    ):
        path = write_series_declaration(
            game_id="MYGAME",
            game_uid="uid_x",
            group_id="vibecode",
            opponent_group="opponent",
            role="police",
            output_dir=tmp_path,
        )
    assert path.name == "declaration_MYGAME.json"


def test_git_clean_field_written(tmp_path):
    """git_clean field is written correctly for clean repos."""
    with (
        patch("league_manager.step0.series_declaration.get_git_sha", return_value="cleansha"),
        patch("league_manager.step0.series_declaration.is_git_clean", return_value=True),
    ):
        path = write_series_declaration(
            game_id="CLEAN01",
            game_uid="uid_clean",
            group_id="vibecode",
            opponent_group="opp",
            role="police",
            output_dir=tmp_path,
        )
    data = json.loads(path.read_text())
    assert data["git_clean"] is True
