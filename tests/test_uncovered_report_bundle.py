"""Tests for reports/bundle.py.

Split from test_uncovered_modules_coverage.py; no LLM, no network.
"""

import asyncio


class TestReportBundleBuilder:
    def test_build_peerruntime_path_with_step0(self, tmp_path):
        """PeerRuntime path: step0_evidence.json + result file present."""
        import json

        from league_manager.reports.bundle import ReportBundleBuilder

        game_id = "peer_game_01"
        (tmp_path / "step0_evidence.json").write_text(json.dumps({"step": 0}))
        (tmp_path / f"result_{game_id}.json").write_text(json.dumps({"winner": "cop"}))

        builder = ReportBundleBuilder(tmp_path)
        ctx = asyncio.run(builder.build(game_id, "cop", {}, result={"winner": "cop"}))
        assert ctx.game_id == game_id
        assert "declaration" in ctx.required_files or "result" in ctx.required_files

    def test_build_peerruntime_path_with_journal(self, tmp_path):
        """PeerRuntime path: journal file + result file."""
        import json

        from league_manager.reports.bundle import ReportBundleBuilder

        game_id = "peer_game_02"
        journal = tmp_path / f"journal_{game_id}_g01.json"
        journal.write_text(json.dumps({"journal": True}))
        (tmp_path / f"result_{game_id}.json").write_text(json.dumps({"winner": "thief"}))

        builder = ReportBundleBuilder(tmp_path)
        ctx = asyncio.run(builder.build(game_id, "thief", {}, metadata={"group_id": "g1"}))
        assert ctx.group_id == "g1"

    def test_build_peerruntime_missing_result_raises(self, tmp_path):
        """PeerRuntime path without result file raises FileNotFoundError."""
        import json

        import pytest

        from league_manager.reports.bundle import ReportBundleBuilder

        game_id = "peer_game_03"
        (tmp_path / "step0_evidence.json").write_text(json.dumps({}))
        # No result file!

        builder = ReportBundleBuilder(tmp_path)
        with pytest.raises(FileNotFoundError):
            asyncio.run(builder.build(game_id, "cop", {}))

    def test_build_gamerunner_path_all_files(self, tmp_path):
        """GameRunner legacy path: all 4 required files present."""
        import json

        from league_manager.reports.bundle import ReportBundleBuilder

        game_id = "legacy_game_01"
        (tmp_path / f"declaration_{game_id}.json").write_text(json.dumps({"decl": True}))
        (tmp_path / f"config_{game_id}_g01.json").write_text(json.dumps({"config": True}))
        (tmp_path / f"log_{game_id}_g01.json").write_text(json.dumps({"log": True}))
        (tmp_path / f"result_{game_id}.json").write_text(json.dumps({"winner": "cop"}))

        builder = ReportBundleBuilder(tmp_path)
        ctx = asyncio.run(
            builder.build(game_id, "cop", {"move_history": []}, result={"winner": "cop"})
        )
        assert ctx.role == "cop"
        assert "declaration" in ctx.required_files

    def test_build_gamerunner_missing_files_raises(self, tmp_path):
        """GameRunner path with missing files raises FileNotFoundError."""
        import pytest

        from league_manager.reports.bundle import ReportBundleBuilder

        game_id = "missing_game"
        builder = ReportBundleBuilder(tmp_path)
        with pytest.raises(FileNotFoundError):
            asyncio.run(builder.build(game_id, "thief", {}))

    def test_collect_optional_files(self, tmp_path):
        """Optional files are collected when they exist."""

        from league_manager.reports.bundle import ReportBundleBuilder

        # Create some optional files
        (tmp_path / "report.json").write_text("{}")
        (tmp_path / "report.md").write_text("# Report")
        (tmp_path / "journal_opt_game_01.json").write_text("{}")

        # Also create required files for a PeerRuntime path
        game_id = "opt_game_01"
        (tmp_path / "step0_evidence.json").write_text("{}")
        (tmp_path / f"result_{game_id}.json").write_text("{}")

        builder = ReportBundleBuilder(tmp_path)
        ctx = asyncio.run(builder.build(game_id, "cop", {}))
        assert "report.json" in ctx.optional_files
        assert "report.md" in ctx.optional_files

    def test_build_with_game_state_timestamps(self, tmp_path):
        """Test that created_at/ended_at from game_state populate timestamps."""

        from league_manager.reports.bundle import ReportBundleBuilder

        game_id = "ts_game_01"
        (tmp_path / "step0_evidence.json").write_text("{}")
        (tmp_path / f"result_{game_id}.json").write_text("{}")

        builder = ReportBundleBuilder(tmp_path)
        ctx = asyncio.run(
            builder.build(
                game_id,
                "thief",
                {"created_at": "2026-01-01T00:00:00", "ended_at": "2026-01-01T01:00:00"},
            )
        )
        assert ctx.start_timestamp == "2026-01-01T00:00:00"
        assert ctx.end_timestamp == "2026-01-01T01:00:00"
