"""Report manager - orchestrate report plugin execution."""

import logging

from agent.reports.base import ReportContext, ReportPlugin, ReportResult

logger = logging.getLogger(__name__)


class ReportManager:
    """Orchestrate execution of report plugins with error isolation."""

    def __init__(self, plugins: list[ReportPlugin]):
        """Initialize manager with plugin instances.

        Args:
            plugins: List of ReportPlugin instances (order matters — file plugins first)
        """
        self.plugins = plugins

    async def generate_all(self, context: ReportContext) -> dict[str, ReportResult]:
        """Execute all plugins and collect results.

        Isolates plugin failures so one failure doesn't stop others.

        Args:
            context: Immutable report context

        Returns:
            Dict mapping plugin.name -> ReportResult
        """
        results = {}

        for plugin in self.plugins:
            try:
                logger.info(f"Executing report plugin: {plugin.name}")
                result = await plugin.generate(context)
                results[plugin.name] = result

                status_emoji = "✓" if result.ok else "✗"
                logger.info(
                    f"Report [{status_emoji}] {plugin.name}: {result.status} → {result.destination or 'N/A'}"  # noqa: E501
                )

            except Exception as e:
                logger.error(f"Plugin {plugin.name} raised exception: {e}", exc_info=True)
                results[plugin.name] = ReportResult(
                    plugin=plugin.name,
                    ok=False,
                    status="failed",
                    error=f"Plugin raised exception: {e}",
                    error_code="plugin_exception",
                )

        return results

    def __len__(self) -> int:
        """Return number of registered plugins."""
        return len(self.plugins)
