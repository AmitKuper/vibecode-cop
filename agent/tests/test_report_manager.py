"""Tests for report plugin manager."""

from pathlib import Path

import pytest

from agent.reports.base import ReportContext, ReportResult
from agent.reports.manager import ReportManager


class MockPlugin:
    """Mock plugin for testing."""

    def __init__(self, name: str, should_fail: bool = False):
        self.name = name
        self.should_fail = should_fail

    async def generate(self, context: ReportContext) -> ReportResult:
        """Mock generate method."""
        if self.should_fail:
            raise RuntimeError(f"Mock error from {self.name}")

        return ReportResult(
            plugin=self.name,
            ok=True,
            status="completed",
            destination=f"/path/{self.name}",
        )


@pytest.fixture
def report_context():
    """Create a test ReportContext."""
    return ReportContext(
        game_id="test_game_001",
        role="cop",
        group_id="test_group",
        opponent_group_id="opponent_group",
        game_dir=Path("/tmp/game_001"),
        game_state={"winner": "cop"},
        result={"winner": "cop"},
        start_timestamp="2026-07-20T00:00:00",
        end_timestamp="2026-07-20T01:00:00",
        config_hash="abc123",
        log_hash="def456",
        required_files={},
        optional_files={},
    )


@pytest.mark.asyncio
async def test_manager_runs_all_plugins(report_context):
    """Manager should run all plugins."""
    plugin1 = MockPlugin("plugin1")
    plugin2 = MockPlugin("plugin2")

    manager = ReportManager([plugin1, plugin2])
    results = await manager.generate_all(report_context)

    assert len(results) == 2
    assert results["plugin1"].ok is True
    assert results["plugin2"].ok is True


@pytest.mark.asyncio
async def test_manager_isolates_failures(report_context):
    """One plugin failure should not stop others."""
    plugin_ok = MockPlugin("ok")
    plugin_fail = MockPlugin("fail", should_fail=True)
    plugin_ok2 = MockPlugin("ok2")

    manager = ReportManager([plugin_ok, plugin_fail, plugin_ok2])
    results = await manager.generate_all(report_context)

    # All plugins should have results
    assert len(results) == 3

    # OK plugins should succeed
    assert results["ok"].ok is True
    assert results["ok2"].ok is True

    # Failed plugin should be marked as failed
    assert results["fail"].ok is False
    assert "Mock error" in results["fail"].error


@pytest.mark.asyncio
async def test_manager_empty_plugins(report_context):
    """Manager with no plugins should return empty results."""
    manager = ReportManager([])
    results = await manager.generate_all(report_context)

    assert len(results) == 0


def test_manager_len():
    """Manager should report number of plugins."""
    plugins = [MockPlugin("p1"), MockPlugin("p2"), MockPlugin("p3")]
    manager = ReportManager(plugins)

    assert len(manager) == 3
