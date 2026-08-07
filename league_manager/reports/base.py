"""Report plugin infrastructure — contracts and interfaces."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ReportContext:
    """Immutable context passed to all report plugins."""

    game_id: str
    role: str  # "cop" or "thief"
    group_id: str
    opponent_group_id: str | None
    game_dir: Path
    game_state: dict
    result: dict | None  # {"winner": "cop"|"thief", ...}
    start_timestamp: str  # ISO 8601
    end_timestamp: str
    config_hash: str | None
    log_hash: str | None
    required_files: dict[str, Path]  # {"declaration": Path, "config": Path, ...}
    optional_files: dict[str, Path]  # {"report_json": Path, "report_md": Path, ...}
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReportResult:
    """Result of a single report plugin execution."""

    plugin: str
    ok: bool
    status: str  # "sent", "skipped", "dry_run", "failed", "draft"
    destination: str | None = None  # email, file path, draft ID, etc.
    error: str | None = None
    error_code: str | None = None  # "gmail_auth_missing", etc.
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Ensure ok=False implies error is set."""
        if not self.ok and not self.error:
            self.error = "Unknown error"


class ReportPlugin(Protocol):
    """Protocol for report plugins."""

    name: str

    async def generate(self, context: ReportContext) -> ReportResult:
        """Generate a report. Must not raise exceptions; return ReportResult instead."""
        ...
