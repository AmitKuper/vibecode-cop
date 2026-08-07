"""Game report plugins — re-exports from league_manager.reports."""

from league_manager.reports.base import ReportPlugin
from league_manager.reports.manager import ReportManager

__all__ = ["ReportPlugin", "ReportManager"]
