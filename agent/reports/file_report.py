"""Write game report to JSON/Markdown file."""

import json
import logging

from agent.reports.base import ReportContext, ReportResult

logger = logging.getLogger(__name__)


class FileReportPlugin:
    """Generate local JSON and Markdown reports."""

    def __init__(self, name: str, report_format: str = "json"):
        """Initialize file report plugin.

        Args:
            name: Plugin name ("file_json" or "file_markdown")
            report_format: "json" or "markdown"
        """
        self.name = name
        self.report_format = report_format

    async def generate(self, context: ReportContext) -> ReportResult:
        """Generate report file."""
        try:
            if self.report_format == "markdown":
                return await self._generate_markdown(context)
            else:
                return await self._generate_json(context)

        except Exception as e:
            logger.error(f"FileReportPlugin {self.name} failed: {e}", exc_info=True)
            return ReportResult(
                plugin=self.name,
                ok=False,
                status="failed",
                error=str(e),
                error_code="file_write_error",
            )

    async def _generate_json(self, context: ReportContext) -> ReportResult:
        """Generate JSON report."""
        report_file = context.game_dir / "report.json"

        report = {
            "game_id": context.game_id,
            "role": context.role,
            "winner": context.result.get("winner") if context.result else None,
            "config_sha256": context.config_hash or "",
            "log_hash": context.log_hash or "",
            "start": context.start_timestamp,
            "end": context.end_timestamp,
            "final_positions": {
                "cop": context.game_state.get("cop_position", [0, 0]),
                "thief": context.game_state.get("thief_position", [6, 6]),
            },
            "move_count": len(context.game_state.get("move_history", [])),
            "move_history": context.game_state.get("move_history", []),
        }

        report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"JSON report written to {report_file}")
        return ReportResult(
            plugin=self.name,
            ok=True,
            status="completed",
            destination=str(report_file),
        )

    async def _generate_markdown(self, context: ReportContext) -> ReportResult:
        """Generate Markdown report."""
        report_file = context.game_dir / "report.md"

        winner = (
            (context.result.get("winner") or "unknown").upper() if context.result else "UNKNOWN"
        )
        cop_pos = context.game_state.get("cop_position", [0, 0])
        thief_pos = context.game_state.get("thief_position", [6, 6])
        move_history = context.game_state.get("move_history", [])

        md = f"""# Game Report: {context.game_id}

## Result
**Winner: {winner}**
**Role:** {context.role}
**Group:** {context.group_id}

## Timeline
- Started: {context.start_timestamp}
- Ended: {context.end_timestamp}

## Final State
- Cop Position: {cop_pos}
- Thief Position: {thief_pos}
- Total Moves: {len(move_history)}

## Move History
| Turn | Cop | Thief |
|------|-----|-------|
"""

        for i, move in enumerate(move_history[:20], 1):  # Show first 20 moves
            cop_move = move.get("cop", "?")
            thief_move = move.get("thief", "?")
            md += f"| {i:3d} | {cop_move:5s} | {thief_move:5s} |\n"

        if len(move_history) > 20:
            md += f"\n... ({len(move_history) - 20} more moves)\n"

        md += "\n## Hashes\n"
        if context.config_hash:
            md += f"- Config: {context.config_hash}\n"
        if context.log_hash:
            md += f"- Log: {context.log_hash}\n"

        report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(report_file, "w") as f:
            f.write(md)

        logger.info(f"Markdown report written to {report_file}")
        return ReportResult(
            plugin=self.name,
            ok=True,
            status="completed",
            destination=str(report_file),
        )
