"""Tests that GameRunner copies real files to agent game dirs before notify."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.game_runner import GameRunner


class TestCopyFilesToAgentDirs:
    def _make_runner(self, tmp_path: Path) -> GameRunner:
        runner = GameRunner(
            cop_url="http://localhost:5000",
            thief_url="http://localhost:5001",
            secret="test-secret",
            config_sha256="a" * 64,
            games_dir=tmp_path / "memory",
        )
        return runner

    def _setup_game_dir(self, runner: GameRunner, game_id: str) -> Path:
        gd = runner.games_dir / game_id
        gd.mkdir(parents=True, exist_ok=True)
        runner._game_dir = gd
        runner._game_id = game_id
        for fname in [
            f"declaration_{game_id}.json",
            f"config_{game_id}_g00.json",
            f"log_{game_id}_g00.json",
            f"result_{game_id}.json",
        ]:
            (gd / fname).write_text(json.dumps({"game_id": game_id}), encoding="utf-8")
        return gd

    def test_copy_files_to_agent_dirs_real_fs(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = self._make_runner(tmp_path)
        game_id = "test_copy_002"
        self._setup_game_dir(runner, game_id)

        runner._copy_files_to_agent_dirs(game_id)

        for role in ("cop", "thief"):
            dst = tmp_path / f"{role}/games/{game_id}"
            files = list(dst.glob("*.json"))
            assert len(files) == 4, f"Expected 4 real files, got {len(files)} in {dst}"
            for f in files:
                content = json.loads(f.read_text())
                assert content.get("game_id") == game_id, "File must be real, not a stub"
                assert "status" not in content, "File must not be a stub"
