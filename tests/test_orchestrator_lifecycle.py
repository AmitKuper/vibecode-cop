"""Tests for AgentOrchestrator Phase 3 v7 lifecycle methods."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_orchestrator(tmp_path, mode_str="DEVELOPMENT", config=None):
    from agent.agent_orchestrator import AgentOrchestrator

    from agent.runtime_mode import RuntimeMode

    mode_map = {
        "DEVELOPMENT": RuntimeMode.DEVELOPMENT,
        "COUNTED": RuntimeMode.COUNTED,
    }
    cfg = config or {}
    return AgentOrchestrator(
        role="cop",
        game_uid="test-game-001",
        grid_size=7,
        mode=mode_map[mode_str],
        work_dir=str(tmp_path),
        config=cfg,
    )


# ---------------------------------------------------------------------------
# 3A: build_step0_declaration
# ---------------------------------------------------------------------------


class TestBuildStep0Declaration:
    def test_build_step0_declaration_fields(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        decl = orch.build_step0_declaration("test-game-001")
        assert decl.model_role == "cop"
        assert decl.model_algorithm == "heuristic"
        assert decl.os_info != ""

    def test_build_step0_declaration_game_uid(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        decl = orch.build_step0_declaration("my-game-xyz")
        assert decl.game_uid == "my-game-xyz"

    def test_build_step0_declaration_config_overrides(self, tmp_path):
        cfg = {
            "model_algorithm": "rl",
            "model_sha256": "abc" * 20,
            "my_endpoint": "http://localhost:5000",
        }
        orch = _make_orchestrator(tmp_path, config=cfg)
        decl = orch.build_step0_declaration("g1")
        assert decl.model_algorithm == "rl"
        assert decl.local_endpoint == "http://localhost:5000"

    def test_build_step0_declaration_git_sha_fallback(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        with patch("subprocess.check_output", side_effect=Exception("no git")):
            decl = orch.build_step0_declaration("g1")
        assert decl.git_sha == "unknown"


# ---------------------------------------------------------------------------
# 3A: validate_counted_declaration
# ---------------------------------------------------------------------------


class TestValidateCountedDeclaration:
    def test_validate_counted_declaration_development_mode_passes(self, tmp_path):
        orch = _make_orchestrator(tmp_path, mode_str="DEVELOPMENT")
        from agent.step0.declaration import PeerDeclaration

        decl = PeerDeclaration(game_uid="g1")
        errors = orch.validate_counted_declaration(decl)
        assert errors == []

    def test_validate_counted_declaration_dev_secret_blocked(self, tmp_path):
        from agent.runtime_mode import RuntimeMode

        # Counted construction is covered by test_codex_counted_composition. This
        # unit isolates declaration validation without weakening its preconditions.
        orch = _make_orchestrator(tmp_path)
        orch.mode = RuntimeMode.COUNTED

        from agent.step0.declaration import PeerDeclaration

        # A bare declaration has placeholder fields — should yield errors
        decl = PeerDeclaration(game_uid="g1")
        errors = orch.validate_counted_declaration(decl)
        # At minimum git_sha, group_id, model_sha256 are invalid
        assert len(errors) > 0

    def test_validate_counted_declaration_skips_when_not_counted(self, tmp_path):
        orch = _make_orchestrator(tmp_path, mode_str="DEVELOPMENT")
        from agent.step0.declaration import PeerDeclaration

        # Even with clearly invalid fields, returns [] in DEVELOPMENT mode
        decl = PeerDeclaration(game_uid="g1", git_sha="", model_sha256="")
        assert orch.validate_counted_declaration(decl) == []


# ---------------------------------------------------------------------------
# 3A: record_step_evidence
# ---------------------------------------------------------------------------


class TestRecordStepEvidence:
    def test_record_step_evidence_appended(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        h = orch.record_step_evidence(
            gamelet=0,
            step=1,
            local_commitment="h" * 64,
            local_move="N",
            received_commitment="r" * 64,
            received_move="S",
        )
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex

    def test_record_step_evidence_persisted(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch.record_step_evidence(gamelet=0, step=1, local_move="E", received_move="W")
        journal = orch.get_journal(0)
        assert len(journal.entries) == 1

    def test_record_step_evidence_multiple_steps(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch.record_step_evidence(gamelet=0, step=1, local_move="N")
        orch.record_step_evidence(gamelet=0, step=2, local_move="S")
        journal = orch.get_journal(0)
        assert len(journal.entries) == 2

    def test_record_step_evidence_chain_grows(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        h1 = orch.record_step_evidence(gamelet=0, step=1)
        h2 = orch.record_step_evidence(gamelet=0, step=2)
        assert h1 != h2


# ---------------------------------------------------------------------------
# 3A: emit_heartbeat
# ---------------------------------------------------------------------------


class TestEmitHeartbeat:
    def test_emit_heartbeat_creates_file(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        hb_path = str(tmp_path / "heartbeat_test-game-001.json")
        orch._watchdog_heartbeat_path = hb_path
        orch.emit_heartbeat(step=3)
        assert Path(hb_path).exists()
        data = json.loads(Path(hb_path).read_text())
        assert data["current_step"] == 3
        assert data["game_uid"] == "test-game-001"

    def test_emit_heartbeat_noop_when_no_path(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        # _watchdog_heartbeat_path is "" by default — should be a no-op
        orch.emit_heartbeat(step=5)  # must not raise


# ---------------------------------------------------------------------------
# 3A: start_watchdog / stop_watchdog
# ---------------------------------------------------------------------------


class TestWatchdog:
    def test_start_stop_watchdog_development_mode(self, tmp_path):
        orch = _make_orchestrator(tmp_path, mode_str="DEVELOPMENT")
        orch.start_watchdog()
        # In DEVELOPMENT mode no subprocess is launched
        assert orch._watchdog_proc is None
        # But heartbeat path is set
        assert orch._watchdog_heartbeat_path != ""
        # And a heartbeat file was written
        assert Path(orch._watchdog_heartbeat_path).exists()
        # stop should be a no-op
        orch.stop_watchdog()

    def test_start_watchdog_sets_paths(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch.start_watchdog()
        assert "heartbeat" in orch._watchdog_heartbeat_path
        assert "watchdog_evidence" in orch._watchdog_evidence_path

    def test_counted_watchdog_uses_negotiated_threshold_and_fails_closed(self, tmp_path):
        from agent.runtime_mode import RuntimeMode

        orch = _make_orchestrator(tmp_path)
        orch.mode = RuntimeMode.COUNTED
        orch.config = {"private_config": {"timeouts": {"watchdog_threshold_seconds": 60}}}
        proc = MagicMock()
        with patch(
            "agent.reliability.watchdog.launch_watchdog_subprocess", return_value=proc
        ) as launch:
            orch.start_watchdog()

        launch.assert_called_once_with(
            orch._watchdog_heartbeat_path,
            orch._watchdog_evidence_path,
            threshold_s=60.0,
        )
        orch.stop_watchdog()

        with (
            patch(
                "agent.reliability.watchdog.launch_watchdog_subprocess",
                side_effect=OSError("spawn denied"),
            ),
            pytest.raises(RuntimeError, match="COUNTED watchdog failed to start"),
        ):
            orch.start_watchdog()

    def test_stop_watchdog_terminates_proc(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        mock_proc = MagicMock()
        orch._watchdog_proc = mock_proc
        orch.stop_watchdog()
        mock_proc.terminate.assert_called_once()

    def test_stop_watchdog_handles_error(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        mock_proc = MagicMock()
        mock_proc.terminate.side_effect = OSError("gone")
        orch._watchdog_proc = mock_proc
        orch.stop_watchdog()  # must not raise


# ---------------------------------------------------------------------------
# 3A: record_match_in_ledger
# ---------------------------------------------------------------------------


class TestRecordMatchInLedger:
    def test_record_match_in_ledger(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch.record_match_in_ledger(
            opponent_id="opponent-A",
            match_id="match-001",
            counted=False,
            declaration_hash="d" * 64,
            result_hash="r" * 64,
        )
        assert orch.league_ledger.counted_match_count() == 0
        entries = orch.league_ledger._entries
        assert len(entries) == 1
        assert entries[0].opponent_id == "opponent-A"

    def test_record_duplicate_counted_opponent_raises(self, tmp_path):
        from agent.step0.league_ledger import LeagueLedgerError

        orch = _make_orchestrator(tmp_path)
        orch.record_match_in_ledger(
            opponent_id="team-XYZ",
            match_id="match-001",
            counted=True,
        )
        with pytest.raises(LeagueLedgerError):
            orch.record_match_in_ledger(
                opponent_id="team-XYZ",
                match_id="match-002",
                counted=True,
            )

    def test_record_non_counted_match_does_not_increment_counted(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        orch.record_match_in_ledger(opponent_id="op", match_id="m1", counted=False)
        orch.record_match_in_ledger(opponent_id="op", match_id="m2", counted=False)
        assert orch.league_ledger.counted_match_count() == 0


# ---------------------------------------------------------------------------
# 3A: send_report_via_gatekeeper
# ---------------------------------------------------------------------------


class TestSendReportViaGatekeeper:
    def test_send_report_requires_gmail_sender(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        # No gmail_sender in config — should raise RuntimeError
        with pytest.raises(RuntimeError, match="gmail_sender"):
            orch.send_report_via_gatekeeper(
                idempotency_key="key-1",
                game_id="game-1",
                result_json='{"winner": "cop"}',
            )

    def test_send_report_uses_gatekeeper_pipeline(self, tmp_path):
        mock_sender = MagicMock(return_value="msg-id-abc")
        cfg = {"gmail_sender": mock_sender}
        orch = _make_orchestrator(tmp_path, config=cfg)
        msg_id = orch.send_report_via_gatekeeper(
            idempotency_key="key-1",
            game_id="game-1",
            result_json='{"winner": "cop"}',
        )
        assert msg_id == "msg-id-abc"
        mock_sender.assert_called_once()

    def test_send_report_reuses_gatekeeper_instance(self, tmp_path):
        mock_sender = MagicMock(return_value="msg-id-xyz")
        cfg = {"gmail_sender": mock_sender}
        orch = _make_orchestrator(tmp_path, config=cfg)
        orch.send_report_via_gatekeeper("k1", "g1", '{"winner": "cop"}')
        gk1 = orch._gatekeeper
        # The same gatekeeper is reused on a second call (even if that call fails)
        with contextlib.suppress(Exception):
            orch.send_report_via_gatekeeper("k2", "g1", '{"winner": "thief"}')
        gk2 = orch._gatekeeper
        assert gk1 is gk2
