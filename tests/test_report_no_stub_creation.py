"""Tests that ReportBundleBuilder raises on missing files instead of creating stubs."""

import pytest
from pathlib import Path

from agent.reports.bundle import ReportBundleBuilder


class TestNoStubCreation:
    @pytest.mark.asyncio
    async def test_missing_required_files_raises(self, tmp_path):
        builder = ReportBundleBuilder(tmp_path)
        with pytest.raises(FileNotFoundError, match="Required report files missing"):
            await builder.build(
                game_id="test_game_001",
                role="cop",
                game_state={"created_at": "2026-07-28T00:00:00", "ended_at": "2026-07-28T01:00:00"},
            )

    @pytest.mark.asyncio
    async def test_no_stub_files_created_on_missing(self, tmp_path):
        builder = ReportBundleBuilder(tmp_path)
        try:
            await builder.build(
                game_id="test_game_002",
                role="cop",
                game_state={"created_at": "2026-07-28T00:00:00"},
            )
        except FileNotFoundError:
            pass
        # Ensure no stubs were silently created
        stubs = list(tmp_path.glob("*.json"))
        assert len(stubs) == 0, f"Unexpected stub files created: {stubs}"

    @pytest.mark.asyncio
    async def test_all_required_files_present_succeeds(self, tmp_path):
        game_id = "test_game_003"
        for fname in [
            f"declaration_{game_id}.json",
            f"config_{game_id}_g00.json",
            f"log_{game_id}_g00.json",
            f"result_{game_id}.json",
        ]:
            (tmp_path / fname).write_text('{"ok": true}', encoding="utf-8")

        builder = ReportBundleBuilder(tmp_path)
        ctx = await builder.build(
            game_id=game_id,
            role="cop",
            game_state={"created_at": "2026-07-28T00:00:00"},
        )
        assert len(ctx.required_files) == 4
