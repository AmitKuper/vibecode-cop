"""Factory for creating report plugins from configuration."""

import logging
from typing import Any

from agent.reports.base import ReportPlugin
from agent.reports.file_report import FileReportPlugin
from agent.reports.gmail_report import GmailReportPlugin

logger = logging.getLogger(__name__)


class ReportPluginFactory:
    """Create and register report plugins from configuration."""

    @staticmethod
    async def from_config(reports_config: dict[str, Any]) -> list[ReportPlugin]:
        """Create plugin instances from config dict.

        Args:
            reports_config: Config from [reports] section:
                {
                    "enabled": true,
                    "plugins": ["file_json", "file_markdown", "gmail"],
                    "file_json": {...},
                    "file_markdown": {...},
                    "gmail": {...}
                }

        Returns:
            List of ReportPlugin instances
        """
        plugins: list[ReportPlugin] = []

        # Check if reports are enabled globally
        if not reports_config.get("enabled", True):
            logger.info("Reports disabled globally")
            return plugins

        # Get list of plugins to load
        plugin_list = reports_config.get("plugins", [])
        logger.info(f"Loading report plugins: {plugin_list}")

        for plugin_name in plugin_list:
            plugin_config = reports_config.get(plugin_name, {})

            # Skip if disabled
            if not plugin_config.get("enabled", True):
                logger.debug(f"Plugin {plugin_name} disabled")
                continue

            try:
                if plugin_name == "file_json":
                    plugin = FileReportPlugin(
                        name="file_json",
                        report_format="json",
                    )
                    plugins.append(plugin)
                    logger.info("Loaded file_json plugin")

                elif plugin_name == "file_markdown":
                    plugin = FileReportPlugin(
                        name="file_markdown",
                        report_format="markdown",
                    )
                    plugins.append(plugin)
                    logger.info("Loaded file_markdown plugin")

                elif plugin_name == "gmail":
                    plugin = GmailReportPlugin(
                        name="gmail",
                        mode=plugin_config.get("mode", "dry_run"),
                        recipient=plugin_config.get("recipient", "example@example.com"),
                        credentials_path=plugin_config.get(
                            "credentials_path", "secrets/gmail/credentials.json"
                        ),
                        token_path=plugin_config.get("token_path", "secrets/gmail/token.json"),
                        attach_required_files=plugin_config.get("attach_required_files", True),
                        attach_markdown_summary=plugin_config.get("attach_markdown_summary", True),
                        max_attachments_mb=plugin_config.get("max_attachments_mb", 20),
                    )
                    plugins.append(plugin)
                    logger.info(f"Loaded gmail plugin (mode={plugin.mode})")

                else:
                    logger.warning(f"Unknown plugin type: {plugin_name}")

            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_name}: {e}", exc_info=True)

        logger.info(f"Loaded {len(plugins)} report plugins")
        return plugins
