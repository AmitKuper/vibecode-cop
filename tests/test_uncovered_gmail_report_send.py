"""Tests for reports/gmail_report.py: send-mode paths.

Split from test_uncovered_modules_coverage.py; no LLM, no network.
"""

import asyncio

from tests.helpers_uncovered import _make_report_context


class TestGmailReportPlugin:
    def _make_ctx(self, game_dir):
        return _make_report_context(game_dir, game_id="game_gmail_01")

    def test_send_mode_refresh_error(self, tmp_path):
        """Generic exception from load_oauth_credentials is caught correctly."""
        from unittest.mock import patch

        from league_manager.reports.gmail_report import GmailReportPlugin

        token_file = tmp_path / "token.json"
        token_file.write_text("{}")

        plugin = GmailReportPlugin(mode="send", token_path=str(token_file))
        ctx = self._make_ctx(tmp_path)

        with patch(
            "league_manager.reports.gmail_report.load_oauth_credentials",
            side_effect=Exception("token refresh failed"),
        ):
            result = asyncio.run(plugin.generate(ctx))

        assert result.ok is False
        assert result.error_code == "gmail_auth_missing"

    def test_send_mode_send_error(self, tmp_path):
        """Exception from gmail_api_send is caught as gmail_send_error."""
        from unittest.mock import MagicMock, patch

        from league_manager.reports.gmail_report import GmailReportPlugin

        token_file = tmp_path / "token.json"
        token_file.write_text("{}")

        plugin = GmailReportPlugin(mode="send", token_path=str(token_file))
        ctx = self._make_ctx(tmp_path)

        with (
            patch(
                "league_manager.reports.gmail_report.load_oauth_credentials",
                return_value=MagicMock(),
            ),
            patch(
                "league_manager.reports.gmail_report.gmail_api_send",
                side_effect=Exception("API error"),
            ),
        ):
            result = asyncio.run(plugin.generate(ctx))

        assert result.ok is False
        assert result.error_code == "gmail_send_error"

    def test_send_mode_success(self, tmp_path):
        """Happy path: send returns ok=True with message_id."""
        from unittest.mock import MagicMock, patch

        from league_manager.reports.gmail_report import GmailReportPlugin

        token_file = tmp_path / "token.json"
        token_file.write_text("{}")

        plugin = GmailReportPlugin(mode="send", token_path=str(token_file))
        ctx = self._make_ctx(tmp_path)

        with (
            patch(
                "league_manager.reports.gmail_report.load_oauth_credentials",
                return_value=MagicMock(),
            ),
            patch(
                "league_manager.reports.gmail_report.gmail_api_send",
                return_value="sent_msg_id_42",
            ),
        ):
            result = asyncio.run(plugin.generate(ctx))

        assert result.ok is True
        assert result.status == "sent"
        assert result.details.get("message_id") == "sent_msg_id_42"
