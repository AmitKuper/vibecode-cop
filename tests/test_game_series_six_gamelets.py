"""Tests for the six-gamelet series runner."""

from unittest.mock import AsyncMock, patch

import pytest

from agent.game_series import GameSeries

# Mandatory fixed scoring values from config/game.json
_SCORING = {
    "capture_cop": 20,  # cop score when cop wins
    "capture_thief": 5,  # thief consolation score when caught
    "survival_cop": 5,  # cop score when thief survives
    "survival_thief": 10,  # thief score when thief survives
    "tie_score": 2,
    "technical_loss": 0,
}


def _make_series(tmp_path, n_gamelets=6):
    return GameSeries(
        cop_url="http://localhost:5000",
        thief_url="http://localhost:5001",
        secret="test-secret",
        config_sha256="a" * 64,
        games_dir=tmp_path / "memory",
        max_turns=35,
        group_name="test",
        n_gamelets=n_gamelets,
    )


def _mock_game_result(winner="cop", audit_ok=True, step=10):
    return {"ok": True, "winner": winner, "audit_ok": audit_ok, "final_step": step}


class TestGameSeriesSixGamelets:
    @pytest.mark.asyncio
    async def test_runs_six_gamelets(self, tmp_path):
        series = _make_series(tmp_path, n_gamelets=6)
        call_count = 0

        async def mock_run_game(**kwargs):
            nonlocal call_count
            call_count += 1
            return _mock_game_result("cop")

        with (
            patch("agent.game_series._load_scoring", return_value=_SCORING),
            patch.object(series, "_make_runner") as mock_runner_factory,
        ):
            mock_runner = AsyncMock()
            mock_runner.run_game = mock_run_game
            mock_runner_factory.return_value = mock_runner
            result = await series.run_series(series_id="test_series_001")

        assert len(result["gamelets"]) == 6
        assert call_count == 6

    @pytest.mark.asyncio
    async def test_gamelet_labels_are_g01_through_g06(self, tmp_path):
        series = _make_series(tmp_path, n_gamelets=6)

        async def mock_run_game(**kwargs):
            return _mock_game_result("thief")

        with (
            patch("agent.game_series._load_scoring", return_value=_SCORING),
            patch.object(series, "_make_runner") as mock_runner_factory,
        ):
            mock_runner = AsyncMock()
            mock_runner.run_game = mock_run_game
            mock_runner_factory.return_value = mock_runner
            result = await series.run_series(series_id="test_series_002")

        labels = [g["gamelet"] for g in result["gamelets"]]
        assert labels == ["g01", "g02", "g03", "g04", "g05", "g06"]

    @pytest.mark.asyncio
    async def test_cop_win_scores_accumulate(self, tmp_path):
        # 3 cop wins: cop gets capture_cop=20 each, thief gets capture_thief=5 each
        series = _make_series(tmp_path, n_gamelets=3)

        async def mock_run_game(**kwargs):
            return _mock_game_result("cop")

        with (
            patch("agent.game_series._load_scoring", return_value=_SCORING),
            patch.object(series, "_make_runner") as mock_runner_factory,
        ):
            mock_runner = AsyncMock()
            mock_runner.run_game = mock_run_game
            mock_runner_factory.return_value = mock_runner
            result = await series.run_series()

        assert result["cop_total"] == 60  # 3 × 20
        assert result["thief_total"] == 15  # 3 × 5 consolation
        assert result["series_winner"] == "cop"

    @pytest.mark.asyncio
    async def test_thief_win_scores_accumulate(self, tmp_path):
        # 3 thief wins: thief gets survival_thief=10 each, cop gets survival_cop=5 each
        series = _make_series(tmp_path, n_gamelets=3)

        async def mock_run_game(**kwargs):
            return _mock_game_result("thief")

        with (
            patch("agent.game_series._load_scoring", return_value=_SCORING),
            patch.object(series, "_make_runner") as mock_runner_factory,
        ):
            mock_runner = AsyncMock()
            mock_runner.run_game = mock_run_game
            mock_runner_factory.return_value = mock_runner
            result = await series.run_series()

        assert result["thief_total"] == 30  # 3 × 10
        assert result["cop_total"] == 15  # 3 × 5
        assert result["series_winner"] == "thief"

    @pytest.mark.asyncio
    async def test_technical_loss_gives_zero_pts(self, tmp_path):
        series = _make_series(tmp_path, n_gamelets=2)

        async def mock_run_game(**kwargs):
            return _mock_game_result("TECHNICAL_LOSS", audit_ok=False)

        with (
            patch("agent.game_series._load_scoring", return_value=_SCORING),
            patch.object(series, "_make_runner") as mock_runner_factory,
        ):
            mock_runner = AsyncMock()
            mock_runner.run_game = mock_run_game
            mock_runner_factory.return_value = mock_runner
            result = await series.run_series()

        for g in result["gamelets"]:
            assert g["cop_pts"] == 0
            assert g["thief_pts"] == 0

    @pytest.mark.asyncio
    async def test_series_tie_when_scores_equal(self, tmp_path):
        # With mandatory scoring, a tie requires 1 cop win + 3 thief wins:
        # cop:   20 + 3×5  = 35   thief: 5 + 3×10 = 35
        series = _make_series(tmp_path, n_gamelets=4)
        winners = iter(["cop", "thief", "thief", "thief"])

        async def mock_run_game(**kwargs):
            return _mock_game_result(next(winners))

        with (
            patch("agent.game_series._load_scoring", return_value=_SCORING),
            patch.object(series, "_make_runner") as mock_runner_factory,
        ):
            mock_runner = AsyncMock()
            mock_runner.run_game = mock_run_game
            mock_runner_factory.return_value = mock_runner
            result = await series.run_series()

        assert result["cop_total"] == result["thief_total"]
        assert result["series_winner"] == "tie"

    @pytest.mark.asyncio
    async def test_series_result_file_written(self, tmp_path):
        series = _make_series(tmp_path, n_gamelets=2)

        async def mock_run_game(**kwargs):
            return _mock_game_result("cop")

        with (
            patch("agent.game_series._load_scoring", return_value=_SCORING),
            patch.object(series, "_make_runner") as mock_runner_factory,
        ):
            mock_runner = AsyncMock()
            mock_runner.run_game = mock_run_game
            mock_runner_factory.return_value = mock_runner
            await series.run_series(series_id="file_test_series")

        result_files = list((tmp_path / "memory").glob("*series*.json"))
        assert len(result_files) == 1
        assert "file_test_series" in result_files[0].name
