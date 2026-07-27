"""Tests that Step-0 declaration includes all required fields."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.game_runner_output import generate_output_files


def _make_mock_runner(tmp_path):
    runner = MagicMock()
    runner.config_sha256 = "a" * 64
    runner.cop_url = "http://localhost:5000"
    runner.thief_url = "http://localhost:5001"
    runner.group_name = "test_group"
    runner._game_dir = tmp_path
    runner._cop_reveals = {}
    runner._thief_reveals = {}
    runner._cop_commits = {}
    runner._thief_commits = {}
    runner.cop_win_score = 5
    runner.thief_win_score = 10
    runner.max_turns = 35
    runner.llm_model = None
    runner.token_budget = None
    return runner


class TestDeclarationRequiredFields:
    @pytest.mark.asyncio
    async def test_declaration_has_game_id(self, tmp_path):
        runner = _make_mock_runner(tmp_path)
        board = MagicMock()
        board.cop_position = [0, 0]
        board.thief_position = [3, 3]
        board.barriers = []

        await generate_output_files(runner, "test_decl_001", {}, board)

        decl = json.loads((tmp_path / "declaration_test_decl_001.json").read_text())
        assert decl["game_id"] == "test_decl_001"

    @pytest.mark.asyncio
    async def test_declaration_has_git_commit(self, tmp_path):
        runner = _make_mock_runner(tmp_path)
        board = MagicMock()
        board.cop_position = [0, 0]
        board.thief_position = [3, 3]
        board.barriers = []

        await generate_output_files(runner, "test_decl_002", {}, board)

        decl = json.loads((tmp_path / "declaration_test_decl_002.json").read_text())
        assert "git_commit" in decl

    @pytest.mark.asyncio
    async def test_declaration_has_hardware_section(self, tmp_path):
        runner = _make_mock_runner(tmp_path)
        board = MagicMock()
        board.cop_position = [0, 0]
        board.thief_position = [3, 3]
        board.barriers = []

        await generate_output_files(runner, "test_decl_003", {}, board)

        decl = json.loads((tmp_path / "declaration_test_decl_003.json").read_text())
        assert "hardware" in decl
        hw = decl["hardware"]
        assert "os" in hw
        assert "python" in hw

    @pytest.mark.asyncio
    async def test_declaration_has_gamelet_field(self, tmp_path):
        runner = _make_mock_runner(tmp_path)
        board = MagicMock()
        board.cop_position = [0, 0]
        board.thief_position = [3, 3]
        board.barriers = []

        await generate_output_files(runner, "test_decl_004", {}, board, gamelet=3)

        decl = json.loads((tmp_path / "declaration_test_decl_004.json").read_text())
        assert decl["gamelet"] == 3

    @pytest.mark.asyncio
    async def test_declaration_has_ram_in_hardware(self, tmp_path):
        runner = _make_mock_runner(tmp_path)
        board = MagicMock()
        board.cop_position = [0, 0]
        board.thief_position = [3, 3]
        board.barriers = []

        await generate_output_files(runner, "test_decl_005", {}, board)

        decl = json.loads((tmp_path / "declaration_test_decl_005.json").read_text())
        # ram_gb may be None if psutil not installed, but key must be present
        assert "ram_gb" in decl["hardware"]

    @pytest.mark.asyncio
    async def test_declaration_has_config_sha256(self, tmp_path):
        runner = _make_mock_runner(tmp_path)
        board = MagicMock()
        board.cop_position = [0, 0]
        board.thief_position = [3, 3]
        board.barriers = []

        await generate_output_files(runner, "test_decl_006", {}, board)

        decl = json.loads((tmp_path / "declaration_test_decl_006.json").read_text())
        assert decl["config_sha256"] == "a" * 64

    @pytest.mark.asyncio
    async def test_config_file_uses_gamelet_in_name(self, tmp_path):
        runner = _make_mock_runner(tmp_path)
        board = MagicMock()
        board.cop_position = [0, 0]
        board.thief_position = [3, 3]
        board.barriers = []

        await generate_output_files(runner, "test_decl_007", {}, board, gamelet=2)

        files = list(tmp_path.glob("config_test_decl_007_g*.json"))
        assert any("g02" in f.name for f in files), f"No g02 config file found: {files}"
