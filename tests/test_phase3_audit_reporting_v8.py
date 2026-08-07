from __future__ import annotations

import pytest

pytest.skip("module removed in restructure", allow_module_level=True)

"""Phase 3 v8 tests: bilateral audit, league ledger, and Gatekeeper wiring."""


import json
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Bilateral AuditSummary exchange tests
# ---------------------------------------------------------------------------


class TestBilateralAuditSummary:
    """Verify that passive side returns nonces + signed AuditSummary."""

    def _make_runtime(self, tmp_path):
        from unittest.mock import MagicMock

        from cop_worker.domain.types import DomainState

        rt = MagicMock()
        rt.role = "thief"
        rt.game_id = "test-game_g1"
        rt.game_dir = tmp_path
        rt.counted_mode = False
        rt.config_sha256 = "c" * 64
        rt._gamelet_number.return_value = 1
        rt._local_step0 = {}
        rt._remote_step0 = {}
        rt._step0_agreements = {}
        rt._public_transition_root = ""
        rt._last_transition_result = None
        rt._domain_state = DomainState(turn=0, cop_position=(0, 0), thief_position=(3, 3))
        rt._my_commits = {
            1: {
                "nonce": "nonce-1",
                "h_commit": "aaa",
                "move": "N",
                "hint": "",
                "intent": "truth",
                "state_hash": "s1",
            },
            2: {
                "nonce": "nonce-2",
                "h_commit": "bbb",
                "move": "S",
                "hint": "",
                "intent": "truth",
                "state_hash": "s2",
            },
        }
        return rt

    def test_handle_passive_final_audit_returns_nonces(self, tmp_path):
        from cop_worker.peer_agent_passive import handle_passive_final_audit

        rt = self._make_runtime(tmp_path)
        msg = MagicMock()
        msg.nonces = {}
        msg.step = 0

        resp = handle_passive_final_audit(rt, "test-game_g1", msg)

        assert resp["ok"] is True
        assert "nonces" in resp
        assert resp["nonces"]["1"] == "nonce-1"
        assert resp["nonces"]["2"] == "nonce-2"

    def test_handle_passive_final_audit_includes_signed_audit_summary(self, tmp_path):
        from cop_worker.peer_agent_passive import handle_passive_final_audit

        rt = self._make_runtime(tmp_path)
        msg = MagicMock()
        msg.nonces = {}
        msg.step = 0

        resp = handle_passive_final_audit(rt, "test-game_g1", msg)

        assert "signed_audit_summary" in resp
        summary_dict = json.loads(resp["signed_audit_summary"])
        assert "summary" in summary_dict
        assert "signature_hex" in summary_dict
        assert len(summary_dict["signature_hex"]) == 128  # Ed25519 = 64 bytes = 128 hex chars

    def test_handle_passive_final_audit_summary_is_verifiable(self, tmp_path):
        from cop_worker.peer_agent_passive import handle_passive_final_audit

        from cop_worker.audit.audit_summary import SignedAuditSummary, verify_audit_summary

        rt = self._make_runtime(tmp_path)
        msg = MagicMock()
        msg.nonces = {}
        msg.step = 0

        resp = handle_passive_final_audit(rt, "test-game_g1", msg)
        signed = SignedAuditSummary.from_dict(json.loads(resp["signed_audit_summary"]))

        assert verify_audit_summary(signed)

    def test_do_final_audit_processes_opponent_summary(self, tmp_path):
        """Active side parses and verifies opponent's signed AuditSummary."""
        import asyncio

        from cop_worker.peer_runtime_audit import do_final_audit

        from cop_worker.audit.audit_summary import (
            AuditSummary,
            create_signed_audit_summary,
        )
        from cop_worker.step0.signing import generate_key_pair

        # Create a fake opponent response with signed summary
        priv, pub = generate_key_pair()
        summary = AuditSummary(
            game_uid="g1",
            gamelet=0,
            expected_steps=0,
            verified_steps=0,
            audit_status="NOT_APPLICABLE",
            public_key_hex=pub.hex(),
        )
        signed = create_signed_audit_summary(summary, priv)

        expected_resp = {
            "ok": True,
            "nonces": {},
            "signed_audit_summary": json.dumps(signed.to_dict()),
        }

        async def _fake_action(*args, **kwargs):
            return expected_resp

        mock_client = MagicMock()
        mock_client.action = _fake_action

        async def _run():
            # Write empty opponent_commitments so NOT_APPLICABLE path is taken
            (tmp_path / "opponent_commitments.json").write_text("{}")
            ok, details = await do_final_audit(
                mock_client,
                "g1",
                "cop",
                "a" * 64,
                {},
                tmp_path,
                "thief",
                0,
                lambda: "2026-01-01T00:00:00Z",
                gamelet=0,
            )
            return ok, details

        mock_coord = MagicMock(
            on_audit_begin=MagicMock(),
            on_final_audit_complete=MagicMock(),
            on_done=MagicMock(),
            on_technical_loss=MagicMock(),
        )
        with patch("agent.mcp.coordinator.get_coordinator", return_value=mock_coord):
            ok, details = asyncio.run(_run())

        assert "opponent_audit_verified" in details
        assert details["opponent_audit_verified"] is True
        assert details["opponent_audit_status"] == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# LeagueLedger wiring tests
# ---------------------------------------------------------------------------


class TestLeagueLedgerWiring:
    def test_record_match_in_ledger_called_in_counted_mode(self, tmp_path):
        """LeagueLedger.append() is called after a counted game completes."""
        from cop_worker.agent_orchestrator import AgentOrchestrator

        from cop_worker.runtime_mode import RuntimeMode

        orch = AgentOrchestrator(
            role="cop",
            game_uid="test-g1",
            grid_size=7,
            mode=RuntimeMode.DEVELOPMENT,
            work_dir=str(tmp_path),
        )

        # Replace league_ledger with a mock
        mock_ledger = MagicMock()
        orch.league_ledger = mock_ledger

        orch.record_match_in_ledger(
            opponent_id="opponent-group",
            match_id="test-game_g1",
            counted=True,
            result_hash="abc123",
        )

        mock_ledger.append.assert_called_once()
        entry = mock_ledger.append.call_args[0][0]
        assert entry.opponent_id == "opponent-group"
        assert entry.match_id == "test-game_g1"
        assert entry.counted is True

    def test_league_ledger_persists_to_disk(self, tmp_path):
        """LeagueLedger records are written to the work_dir file."""
        from cop_worker.agent_orchestrator import AgentOrchestrator

        from cop_worker.runtime_mode import RuntimeMode

        orch = AgentOrchestrator(
            role="cop",
            game_uid="test-g2",
            grid_size=7,
            mode=RuntimeMode.DEVELOPMENT,
            work_dir=str(tmp_path),
        )
        orch.record_match_in_ledger(
            opponent_id="opp-group-x",
            match_id="test-game_g2",
            counted=False,
        )
        ledger_path = tmp_path / "league_ledger.json"
        assert ledger_path.exists()


# ---------------------------------------------------------------------------
# Gatekeeper wiring tests
# ---------------------------------------------------------------------------


class TestGatekeeperWiring:
    def test_send_report_via_gatekeeper_calls_sender(self, tmp_path):
        """Gatekeeper.send() is invoked with valid JSON body."""
        from cop_worker.agent_orchestrator import AgentOrchestrator

        from cop_worker.runtime_mode import RuntimeMode

        sent = []

        def fake_sender(to, subject, body, attachments=None):
            sent.append({"to": to, "subject": subject, "body": body})
            return "msg-id-001"

        orch = AgentOrchestrator(
            role="cop",
            game_uid="test-g3",
            grid_size=7,
            mode=RuntimeMode.DEVELOPMENT,
            work_dir=str(tmp_path),
            config={"gmail_sender": fake_sender},
        )

        result_json = json.dumps({"ok": True, "game_id": "test-g3", "winner": "cop"})
        msg_id = orch.send_report_via_gatekeeper(
            idempotency_key="test-g3_cop",
            game_id="test-g3",
            result_json=result_json,
        )

        assert msg_id == "msg-id-001"
        assert len(sent) == 1
        assert sent[0]["body"] == result_json

    def test_gatekeeper_rejects_plain_text_body(self, tmp_path):
        """Gatekeeper must reject non-JSON report body."""
        from cop_worker.agent_orchestrator import AgentOrchestrator

        from cop_worker.runtime_mode import RuntimeMode
        from league_manager.gmail.gatekeeper import GatekeeperError

        def fake_sender(*args, **kwargs):
            return "msg-id"

        orch = AgentOrchestrator(
            role="cop",
            game_uid="test-g4",
            grid_size=7,
            mode=RuntimeMode.DEVELOPMENT,
            work_dir=str(tmp_path),
            config={"gmail_sender": fake_sender},
        )

        import pytest

        with pytest.raises(GatekeeperError):
            orch.send_report_via_gatekeeper(
                idempotency_key="test-g4_cop",
                game_id="test-g4",
                result_json="Plain text report",
            )


# ---------------------------------------------------------------------------
# Passive final_audit handler registration test
# ---------------------------------------------------------------------------


class TestPeerAgentRuntimeFinalAuditRouting:
    def test_on_action_routes_final_audit_to_handler(self, tmp_path):
        """PeerAgentRuntime._on_action() calls handle_passive_final_audit for final_audit."""
        from cop_worker.peer_agent_runtime import PeerAgentRuntime

        with (
            patch("agent.peer_agent_runtime.AgentMCPServer"),
            patch("agent.peer_agent_runtime.PeerRuntime") as mock_pr,
        ):
            rt_instance = MagicMock()
            rt_instance._my_commits = {}
            rt_instance.game_id = "g1"
            rt_instance.game_dir = tmp_path
            mock_pr.return_value = rt_instance

            par = PeerAgentRuntime(
                role="thief",
                secret="s",
                config_sha256="a" * 64,
                opponent_url="http://localhost:6000/mcp",
                games_dir=tmp_path,
            )
            par._peer_runtime = rt_instance
            par._rules_ref = []

            msg = MagicMock()
            msg.phase = "final_audit"
            msg.nonces = {}

            with patch("agent.peer_agent_runtime.handle_passive_final_audit") as mock_hpfa:
                mock_hpfa.return_value = {"ok": True, "nonces": {}, "signed_audit_summary": "{}"}
                result = par._on_action("g1", msg)

            mock_hpfa.assert_called_once_with(rt_instance, "g1", msg)
            assert result["ok"] is True
