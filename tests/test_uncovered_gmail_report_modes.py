"""Tests for reports/gmail_report.py: mode handling and auth errors.

Split from test_uncovered_modules_coverage.py; no LLM, no network.
"""

import asyncio

from tests.helpers_uncovered import _make_report_context


class TestGmailReportPlugin:
    def _make_ctx(self, game_dir):
        return _make_report_context(game_dir, game_id="game_gmail_01")

    def test_disabled_mode_returns_skipped(self, tmp_path):
        from league_manager.reports.gmail_report import GmailReportPlugin

        plugin = GmailReportPlugin(mode="disabled")
        ctx = self._make_ctx(tmp_path)
        result = asyncio.run(plugin.generate(ctx))
        assert result.ok is True
        assert result.status == "skipped"

    def test_dry_run_mode_creates_preview(self, tmp_path):
        from league_manager.reports.gmail_report import GmailReportPlugin

        plugin = GmailReportPlugin(mode="dry_run", recipient="test@example.com")
        ctx = self._make_ctx(tmp_path)
        result = asyncio.run(plugin.generate(ctx))
        assert result.ok is True
        assert result.status == "dry_run"
        preview = tmp_path / "game_gmail_01_email_preview.txt"
        assert preview.exists()

    def test_draft_mode_creates_eml(self, tmp_path):
        from league_manager.reports.gmail_report import GmailReportPlugin

        plugin = GmailReportPlugin(mode="draft", recipient="test@example.com")
        ctx = self._make_ctx(tmp_path)
        result = asyncio.run(plugin.generate(ctx))
        assert result.ok is True
        assert result.status == "draft"
        eml = tmp_path / "game_gmail_01.eml"
        assert eml.exists()

    def test_send_mode_missing_token(self, tmp_path):
        from league_manager.reports.gmail_report import GmailReportPlugin

        plugin = GmailReportPlugin(
            mode="send",
            token_path=str(tmp_path / "nonexistent_token.json"),
        )
        ctx = self._make_ctx(tmp_path)
        result = asyncio.run(plugin.generate(ctx))
        assert result.ok is False
        assert result.error_code == "gmail_auth_missing"

    def test_send_mode_auth_runtime_error(self, tmp_path):
        """RuntimeError from load_oauth_credentials is caught correctly."""
        from unittest.mock import patch

        from league_manager.reports.gmail_report import GmailReportPlugin

        # Create a fake token file so token_path.exists() passes
        token_file = tmp_path / "token.json"
        token_file.write_text("{}")

        plugin = GmailReportPlugin(mode="send", token_path=str(token_file))
        ctx = self._make_ctx(tmp_path)

        with patch(
            "league_manager.reports.gmail_report.load_oauth_credentials",
            side_effect=RuntimeError("need re-authorize"),
        ):
            result = asyncio.run(plugin.generate(ctx))

        assert result.ok is False
        assert result.error_code == "gmail_auth_missing"

    def test_invalid_mode(self, tmp_path):
        """Unknown mode returns invalid_mode error code."""
        from league_manager.reports.gmail_report import GmailReportPlugin

        plugin = GmailReportPlugin(mode="unknown_mode")
        ctx = self._make_ctx(tmp_path)
        result = asyncio.run(plugin.generate(ctx))
        assert result.ok is False
        assert result.error_code == "invalid_mode"
