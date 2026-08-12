"""Tests for reports/file_report.py.

Split from test_uncovered_modules_coverage.py; no LLM, no network.
"""

import asyncio

from tests.helpers_uncovered import _make_report_context


class TestFileReportPlugin:
    def test_generate_json_success(self, tmp_path):
        from league_manager.reports.file_report import FileReportPlugin

        ctx = _make_report_context(tmp_path)
        plugin = FileReportPlugin("file_json", report_format="json")
        result = asyncio.run(plugin.generate(ctx))
        assert result.ok is True
        assert result.status == "completed"
        assert (tmp_path / "report.json").exists()

    def test_generate_json_content(self, tmp_path):
        import json

        from league_manager.reports.file_report import FileReportPlugin

        ctx = _make_report_context(tmp_path)
        plugin = FileReportPlugin("file_json", report_format="json")
        asyncio.run(plugin.generate(ctx))
        data = json.loads((tmp_path / "report.json").read_text())
        assert data["game_id"] == "game_001"
        assert data["winner"] == "thief"
        assert data["move_count"] == 2

    def test_generate_markdown_success(self, tmp_path):
        from league_manager.reports.file_report import FileReportPlugin

        ctx = _make_report_context(tmp_path)
        plugin = FileReportPlugin("file_md", report_format="markdown")
        result = asyncio.run(plugin.generate(ctx))
        assert result.ok is True
        assert (tmp_path / "report.md").exists()

    def test_generate_markdown_content(self, tmp_path):
        from league_manager.reports.file_report import FileReportPlugin

        ctx = _make_report_context(tmp_path)
        plugin = FileReportPlugin("file_md", report_format="markdown")
        asyncio.run(plugin.generate(ctx))
        content = (tmp_path / "report.md").read_text()
        assert "game_001" in content
        assert "THIEF" in content
        assert "| Turn |" in content

    def test_generate_markdown_many_moves(self, tmp_path):
        """Verify truncation path (>20 moves) is exercised."""
        from league_manager.reports.base import ReportContext
        from league_manager.reports.file_report import FileReportPlugin

        ctx = ReportContext(
            game_id="game_002",
            role="cop",
            group_id="g1",
            opponent_group_id=None,
            game_dir=tmp_path,
            game_state={
                "cop_position": [0, 0],
                "thief_position": [6, 6],
                "move_history": [{"cop": "N", "thief": "S"}] * 25,
            },
            result={"winner": "cop"},
            start_timestamp="2026-01-01T00:00:00",
            end_timestamp="2026-01-01T00:10:00",
            config_hash=None,
            log_hash=None,
            required_files={},
            optional_files={},
        )
        plugin = FileReportPlugin("file_md", report_format="markdown")
        result = asyncio.run(plugin.generate(ctx))
        assert result.ok is True
        content = (tmp_path / "report.md").read_text()
        assert "more moves" in content

    def test_generate_json_no_result(self, tmp_path):
        """Exercise result=None branch."""
        from league_manager.reports.base import ReportContext
        from league_manager.reports.file_report import FileReportPlugin

        ctx = ReportContext(
            game_id="game_003",
            role="thief",
            group_id="g1",
            opponent_group_id=None,
            game_dir=tmp_path,
            game_state={},
            result=None,
            start_timestamp="2026-01-01T00:00:00",
            end_timestamp="2026-01-01T00:05:00",
            config_hash=None,
            log_hash=None,
            required_files={},
            optional_files={},
        )
        plugin = FileReportPlugin("file_json")
        result = asyncio.run(plugin.generate(ctx))
        assert result.ok is True

    def test_generate_error_path(self, tmp_path):
        """Force an exception by making the path unwritable."""
        from unittest.mock import patch

        from league_manager.reports.file_report import FileReportPlugin

        ctx = _make_report_context(tmp_path)
        plugin = FileReportPlugin("file_json")

        with patch("builtins.open", side_effect=PermissionError("no write")):
            result = asyncio.run(plugin.generate(ctx))

        assert result.ok is False
        assert result.error_code == "file_write_error"
