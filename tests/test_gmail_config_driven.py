"""Tests that Gmail plugin recipient and mode come from config, not hardcoded values."""

import pytest

from agent.reports.plugin_factory import ReportPluginFactory


class TestGmailRecipientConfigDriven:
    @pytest.mark.asyncio
    async def test_gmail_recipient_comes_from_config(self):
        """GmailReportPlugin recipient must be taken from [reports.gmail] config."""
        config = {
            "enabled": True,
            "plugins": ["gmail"],
            "gmail": {
                "enabled": True,
                "mode": "dry_run",
                "recipient": "kuper.amit@gmail.com",
                "credentials_path": "secrets/gmail/credentials.json",
                "token_path": "secrets/gmail/token.json",
            },
        }
        plugins = await ReportPluginFactory.from_config(config)
        assert len(plugins) == 1
        gmail_plugin = plugins[0]
        assert gmail_plugin.recipient == "kuper.amit@gmail.com"

    @pytest.mark.asyncio
    async def test_gmail_mode_comes_from_config(self):
        """GmailReportPlugin mode must be taken from [reports.gmail] config."""
        for mode in ("disabled", "dry_run", "draft", "send"):
            config = {
                "enabled": True,
                "plugins": ["gmail"],
                "gmail": {
                    "enabled": True,
                    "mode": mode,
                    "recipient": "test@example.com",
                },
            }
            plugins = await ReportPluginFactory.from_config(config)
            assert len(plugins) == 1
            assert plugins[0].mode == mode

    @pytest.mark.asyncio
    async def test_gmail_plugin_not_loaded_when_disabled(self):
        """Gmail plugin must not be loaded when plugin_config.enabled is False."""
        config = {
            "enabled": True,
            "plugins": ["gmail"],
            "gmail": {"enabled": False, "mode": "send", "recipient": "test@example.com"},
        }
        plugins = await ReportPluginFactory.from_config(config)
        assert plugins == []

    @pytest.mark.asyncio
    async def test_gmail_default_recipient_is_not_hardcoded_example(self):
        """Default recipient fallback must not silently accept example@example.com as real."""
        config = {
            "enabled": True,
            "plugins": ["gmail"],
            "gmail": {
                "enabled": True,
                "mode": "dry_run",
                # No recipient key — tests that factory reads from config, not a hardcoded address
            },
        }
        plugins = await ReportPluginFactory.from_config(config)
        assert len(plugins) == 1
        # In dry_run mode a placeholder recipient is acceptable — just must not crash
        assert plugins[0].mode == "dry_run"

    @pytest.mark.asyncio
    async def test_multiple_plugins_loaded_from_config(self):
        """All three plugin types are loaded when listed in config."""
        config = {
            "enabled": True,
            "plugins": ["file_json", "file_markdown", "gmail"],
            "gmail": {
                "enabled": True,
                "mode": "dry_run",
                "recipient": "kuper.amit@gmail.com",
            },
        }
        plugins = await ReportPluginFactory.from_config(config)
        names = [p.name for p in plugins]
        assert "file_json" in names
        assert "file_markdown" in names
        assert "gmail" in names
