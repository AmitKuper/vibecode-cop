"""Tests for Gmail plugin dry_run mode."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from agent.reports.base import ReportContext
from agent.reports.gmail_report import GmailReportPlugin


@pytest.fixture
def report_context():
    """Create a test ReportContext."""
    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create optional files
        (tmpdir_path / "report.md").write_text("# Test Report\n")
        (tmpdir_path / "report.json").write_text("{}")

        yield ReportContext(
            game_id="test_game_001",
            role="cop",
            group_id="test_group",
            opponent_group_id="opponent_group",
            game_dir=tmpdir_path,
            game_state={"winner": "cop", "cop_position": [3, 3]},
            result={"winner": "cop"},
            start_timestamp="2026-07-20T00:00:00",
            end_timestamp="2026-07-20T01:00:00",
            config_hash="abc123",
            log_hash="def456",
            required_files={
                "declaration": tmpdir_path / "declaration_test_game_001.json",
                "config": tmpdir_path / "config_test_game_001_g00.json",
                "log": tmpdir_path / "log_test_game_001_g00.json",
                "result": tmpdir_path / "result_test_game_001.json",
            },
            optional_files={
                "report.json": tmpdir_path / "report.json",
                "report.md": tmpdir_path / "report.md",
            },
        )


@pytest.mark.asyncio
async def test_gmail_dry_run_no_credentials(report_context):
    """Dry-run mode should work without Gmail credentials."""
    plugin = GmailReportPlugin(mode="dry_run", recipient="test@example.com")
    result = await plugin.generate(report_context)

    assert result.ok is True
    assert result.status == "dry_run"
    assert "email_preview" in result.destination


@pytest.mark.asyncio
async def test_gmail_dry_run_creates_preview_file(report_context):
    """Dry-run should create a local .txt preview file."""
    plugin = GmailReportPlugin(mode="dry_run", recipient="test@example.com")
    result = await plugin.generate(report_context)

    preview_file = Path(result.destination)
    assert preview_file.exists()

    content = preview_file.read_text()
    assert "Subject:" in content
    assert "test@example.com" in content
    assert "BODY" in content


@pytest.mark.asyncio
async def test_gmail_disabled(report_context):
    """Disabled mode should skip silently."""
    plugin = GmailReportPlugin(mode="disabled", recipient="test@example.com")
    result = await plugin.generate(report_context)

    assert result.ok is True
    assert result.status == "skipped"


@pytest.mark.asyncio
async def test_gmail_send_requires_token(report_context):
    """Send mode should fail if token is missing."""
    plugin = GmailReportPlugin(
        mode="send",
        recipient="test@example.com",
        token_path="/nonexistent/token.json",
    )
    result = await plugin.generate(report_context)

    assert result.ok is False
    assert result.status == "failed"
    assert "auth_missing" in result.error_code
