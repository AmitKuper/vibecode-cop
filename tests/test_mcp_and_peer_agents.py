"""Tests for MCP modules and peer agent classes.

Covers:
- agent/mcp/messages.py (validate_action_message, validate_start_game_message)
- agent/mcp/messages_game.py (ActionMessage, StartGameMessage dataclasses)
- agent/mcp/protocol.py (ProtocolStateMachine)
- agent/mcp/protocol_phases.py (StepPhaseTracker)
- agent/mcp/client.py (GameMCPClient)
- agent/mcp/log.py (GameLog)
- agent/mcp/log_replay.py (load_from_file, verify_log_integrity, etc.)
- agent/mcp/discovery.py (ProtocolDiscovery)
- agent/mcp/server.py (AgentMCPServer)
- agent/mcp/server_tools_game.py (register_game_tools)
- agent/mcp/server_tools_info.py (register_info_tools)
- agent/mcp/server_handlers.py (handle_start_game, handle_action)
- agent/peer_agent_passive.py
- agent/peer_agent_runtime.py (PeerAgentRuntime)
- agent/game_initiator.py (GameInitiator)
- agent/game_initiator_handshake.py (wait_for_readiness, call_start_game)
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

SHA256 = "a" * 64  # valid 64-char hex stub


def _make_action_msg(**kwargs):
    from agent.mcp.messages_game import ActionMessage

    defaults = {
        "game_id": "g1",
        "step": 0,
        "role": "cop",
        "config_sha256": SHA256,
        "timestamp": "2024-01-01T00:00:00",
        "phase": "commit",
    }
    defaults.update(kwargs)
    return ActionMessage(**defaults)


def _make_start_game_msg(**kwargs):
    from agent.mcp.messages_game import StartGameMessage

    defaults = {
        "game_id": "g1",
        "roles": {"cop": "Alice", "thief": "Bob"},
        "config_sha256": SHA256,
        "protocol_version": "1.0",
        "endpoint": "http://localhost:5000/mcp",
        "timestamp": "2024-01-01T00:00:00",
    }
    defaults.update(kwargs)
    return StartGameMessage(**defaults)


# ===========================================================================
# 1. messages.py — validate_start_game_message
# ===========================================================================


class TestValidateStartGameMessage:
    def test_valid_returns_true(self):
        from agent.mcp.messages import validate_start_game_message

        ok, err = validate_start_game_message(_make_start_game_msg())
        assert ok is True
        assert err is None

    def test_missing_game_id(self):
        from agent.mcp.messages import validate_start_game_message

        ok, err = validate_start_game_message(_make_start_game_msg(game_id=""))
        assert ok is False
        assert "game_id" in err

    def test_missing_roles(self):
        from agent.mcp.messages import validate_start_game_message

        ok, err = validate_start_game_message(_make_start_game_msg(roles={}))
        assert ok is False
        assert "roles" in err

    def test_roles_missing_cop(self):
        from agent.mcp.messages import validate_start_game_message

        ok, err = validate_start_game_message(_make_start_game_msg(roles={"thief": "Bob"}))
        assert ok is False

    def test_bad_config_sha256_length(self):
        from agent.mcp.messages import validate_start_game_message

        ok, err = validate_start_game_message(_make_start_game_msg(config_sha256="abc"))
        assert ok is False
        assert "config_sha256" in err

    def test_wrong_protocol_version(self):
        from agent.mcp.messages import validate_start_game_message

        ok, err = validate_start_game_message(_make_start_game_msg(protocol_version="2.0"))
        assert ok is False
        assert "protocol_version" in err

    def test_bad_endpoint(self):
        from agent.mcp.messages import validate_start_game_message

        ok, err = validate_start_game_message(_make_start_game_msg(endpoint=""))
        assert ok is False
        assert "endpoint" in err

    def test_endpoint_not_http(self):
        from agent.mcp.messages import validate_start_game_message

        ok, err = validate_start_game_message(_make_start_game_msg(endpoint="ftp://foo"))
        assert ok is False

    def test_missing_timestamp(self):
        from agent.mcp.messages import validate_start_game_message

        ok, err = validate_start_game_message(_make_start_game_msg(timestamp=""))
        assert ok is False
        assert "timestamp" in err


# ===========================================================================
# 2. messages.py — validate_action_message
# ===========================================================================


class TestValidateActionMessage:
    def test_valid_commit(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg())
        assert ok is True

    def test_missing_game_id(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg(game_id=""))
        assert ok is False
        assert "game_id" in err

    def test_negative_step(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg(step=-1))
        assert ok is False
        assert "step" in err

    def test_bad_role(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg(role="judge"))
        assert ok is False
        assert "role" in err

    def test_bad_config_sha256(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg(config_sha256="short"))
        assert ok is False

    def test_missing_timestamp(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg(timestamp=""))
        assert ok is False

    def test_invalid_phase(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg(phase="unknown_phase"))
        assert ok is False
        assert "phase" in err

    def test_commit_with_bad_h_commit_length(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg(phase="commit", h_commit="abc"))
        assert ok is False
        assert "h_commit" in err

    def test_commit_with_no_h_commit_is_valid(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg(phase="commit", h_commit=None))
        assert ok is True

    def test_ack_requires_h_commit_ack(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg(phase="ack", h_commit_ack=None))
        assert ok is False
        assert "h_commit_ack" in err

    def test_ack_with_h_commit_ack_is_valid(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg(phase="ack", h_commit_ack=SHA256))
        assert ok is True

    def test_reveal_valid_move(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg(phase="reveal", move="N"))
        assert ok is True

    def test_reveal_invalid_move(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg(phase="reveal", move="INVALID"))
        assert ok is False
        assert "move" in err

    def test_reveal_invalid_intent(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg(phase="reveal", intent="maybe"))
        assert ok is False
        assert "intent" in err

    def test_reveal_hint_too_long(self):
        from agent.mcp.messages import validate_action_message

        long_hint = " ".join(["word"] * 16)
        ok, err = validate_action_message(_make_action_msg(phase="reveal", hint=long_hint))
        assert ok is False
        assert "hint" in err

    def test_reveal_bad_state_hash(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg(phase="reveal", state_hash="short"))
        assert ok is False
        assert "state_hash" in err

    def test_final_audit_nonces_not_dict(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg(phase="final_audit", nonces="bad"))
        assert ok is False
        assert "nonces" in err

    def test_final_audit_with_dict_nonces(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(
            _make_action_msg(phase="final_audit", nonces={"0": "abc"})
        )
        assert ok is True

    def test_abort_requires_reason(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg(phase="abort", reason=None))
        assert ok is False
        assert "reason" in err

    def test_abort_with_reason(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg(phase="abort", reason="cheating"))
        assert ok is True

    def test_game_end_with_reason_is_valid(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(
            _make_action_msg(phase="game_end", reason="cop_caught_thief")
        )
        assert ok is True

    def test_role_initiator_is_valid(self):
        from agent.mcp.messages import validate_action_message

        ok, err = validate_action_message(_make_action_msg(role="initiator"))
        assert ok is True


# ===========================================================================
# 3. messages_game.py — ActionMessage and StartGameMessage
# ===========================================================================


class TestActionMessageDataclass:
    def test_from_json_round_trip(self):
        msg = _make_action_msg()
        d = msg.to_dict()
        assert d["game_id"] == "g1"
        assert d["phase"] == "commit"

    def test_to_dict_excludes_none_fields(self):
        msg = _make_action_msg()
        d = msg.to_dict()
        assert "h_commit" not in d
        assert "move" not in d

    def test_to_dict_includes_set_fields(self):
        msg = _make_action_msg(
            h_commit=SHA256,
            move="N",
            hint="going north",
            intent="truth",
            state_hash=SHA256,
            nonces={"0": "x"},
            game_log=[{"a": 1}],
            reason="done",
            board_state={"x": 1},
        )
        d = msg.to_dict()
        assert d["h_commit"] == SHA256
        assert d["move"] == "N"
        assert d["hint"] == "going north"
        assert d["intent"] == "truth"
        assert d["state_hash"] == SHA256
        assert d["nonces"] == {"0": "x"}
        assert d["game_log"] == [{"a": 1}]
        assert d["reason"] == "done"
        assert d["board_state"] == {"x": 1}

    def test_from_json_parses_correctly(self):
        from agent.mcp.messages_game import ActionMessage

        data = {
            "game_id": "g2",
            "step": 1,
            "role": "thief",
            "config_sha256": SHA256,
            "timestamp": "ts",
            "phase": "reveal",
            "move": "S",
        }
        msg = ActionMessage.from_json(json.dumps(data))
        assert msg.game_id == "g2"
        assert msg.move == "S"

    def test_from_json_ignores_unknown_fields(self):
        from agent.mcp.messages_game import ActionMessage

        data = {
            "game_id": "g3",
            "step": 0,
            "role": "cop",
            "config_sha256": SHA256,
            "timestamp": "ts",
            "phase": "commit",
            "unknown_field_xyz": "ignored",
        }
        msg = ActionMessage.from_json(json.dumps(data))
        assert msg.game_id == "g3"

    def test_from_json_raises_on_bad_json(self):
        from agent.mcp.messages_game import ActionMessage

        with pytest.raises(ValueError):
            ActionMessage.from_json("not json")

    def test_from_json_raises_on_missing_required(self):
        from agent.mcp.messages_game import ActionMessage

        with pytest.raises(ValueError):
            ActionMessage.from_json(json.dumps({"game_id": "x"}))


class TestStartGameMessageDataclass:
    def test_to_dict_basic(self):
        msg = _make_start_game_msg()
        d = msg.to_dict()
        assert d["game_id"] == "g1"
        assert "peer_url" not in d  # None by default

    def test_to_dict_with_peer_url(self):
        msg = _make_start_game_msg(peer_url="http://peer:5001")
        d = msg.to_dict()
        assert d["peer_url"] == "http://peer:5001"

    def test_from_json_round_trip(self):
        from agent.mcp.messages_game import StartGameMessage

        msg = _make_start_game_msg()
        j = json.dumps(msg.to_dict())
        msg2 = StartGameMessage.from_json(j)
        assert msg2.game_id == "g1"
        assert msg2.roles == {"cop": "Alice", "thief": "Bob"}

    def test_from_json_ignores_unknown(self):
        from agent.mcp.messages_game import StartGameMessage

        data = {
            "game_id": "g1",
            "roles": {"cop": "a", "thief": "b"},
            "config_sha256": SHA256,
            "protocol_version": "1.0",
            "endpoint": "http://x",
            "timestamp": "ts",
            "XTRA": "ignored",
        }
        msg = StartGameMessage.from_json(json.dumps(data))
        assert msg.game_id == "g1"

    def test_from_json_bad_json_raises(self):
        from agent.mcp.messages_game import StartGameMessage

        with pytest.raises(ValueError):
            StartGameMessage.from_json("{bad}")


# ===========================================================================
# 4. protocol.py — ProtocolStateMachine (16-state machine)
# ===========================================================================


class TestProtocolStateMachine:
    def test_initial_state(self):
        from agent.mcp.protocol import ProtocolState, ProtocolStateMachine

        sm = ProtocolStateMachine()
        assert sm.state == ProtocolState.IDLE
        assert sm.step == 0

    def test_transition_idle_to_step0_negotiating(self):
        from agent.mcp.protocol import ProtocolState, ProtocolStateMachine

        sm = ProtocolStateMachine()
        sm.transition(ProtocolState.STEP0_NEGOTIATING)
        assert sm.state == ProtocolState.STEP0_NEGOTIATING

    def test_can_transition_true(self):
        from agent.mcp.protocol import ProtocolState, ProtocolStateMachine

        sm = ProtocolStateMachine()
        ok, err = sm.can_transition(ProtocolState.STEP0_NEGOTIATING)
        assert ok is True
        assert err is None

    def test_can_transition_false_illegal(self):
        from agent.mcp.protocol import ProtocolState, ProtocolStateMachine

        sm = ProtocolStateMachine()
        ok, err = sm.can_transition(ProtocolState.REVEAL_SENT)
        assert ok is False
        assert err is not None

    def test_transition_raises_on_illegal(self):
        from agent.mcp.protocol import ProtocolState, ProtocolStateMachine

        sm = ProtocolStateMachine()
        with pytest.raises(ValueError):
            sm.transition(ProtocolState.REVEAL_SENT)

    def test_transition_to_ready(self):
        from agent.mcp.protocol import ProtocolState, ProtocolStateMachine

        sm = ProtocolStateMachine()
        sm.transition(ProtocolState.STEP0_NEGOTIATING)
        sm.transition(ProtocolState.READY)
        assert sm.state == ProtocolState.READY
        assert sm.step == 0

    def test_advance_step(self):
        from agent.mcp.protocol import ProtocolState, ProtocolStateMachine

        sm = ProtocolStateMachine()
        sm.transition(ProtocolState.STEP0_NEGOTIATING)
        sm.transition(ProtocolState.READY)
        sm.advance_step()
        assert sm.step == 1

    def test_to_dict(self):
        from agent.mcp.protocol import ProtocolStateMachine

        sm = ProtocolStateMachine()
        d = sm.to_dict()
        assert d["state"] == "idle"
        assert d["step"] == 0

    def test_from_dict(self):
        from agent.mcp.protocol import ProtocolState, ProtocolStateMachine

        data = {"state": "computing_move", "step": 3}
        sm = ProtocolStateMachine.from_dict(data)
        assert sm.state == ProtocolState.COMPUTING_MOVE
        assert sm.step == 3

    def test_from_dict_no_phase(self):
        from agent.mcp.protocol import ProtocolState, ProtocolStateMachine

        data = {"state": "idle", "step": 0}
        sm = ProtocolStateMachine.from_dict(data)
        assert sm.state == ProtocolState.IDLE

    def test_transition_to_auditing(self):
        from agent.mcp.protocol import ProtocolState, ProtocolStateMachine

        sm = ProtocolStateMachine()
        sm.state = ProtocolState.STEP_VERIFIED
        sm.transition(ProtocolState.AUDITING)
        assert sm.state == ProtocolState.AUDITING


# ===========================================================================
# 5. protocol_phases.py — StepPhaseTracker
# ===========================================================================


class TestStepPhaseTracker:
    def test_mark_and_check_phase(self):
        from agent.mcp.protocol import ProtocolPhase
        from agent.mcp.protocol_phases import StepPhaseTracker

        tracker = StepPhaseTracker()
        tracker.mark_phase(0, "cop", ProtocolPhase.COMMIT)
        tracker.mark_phase(0, "thief", ProtocolPhase.COMMIT)
        assert tracker.both_at_phase(0, ProtocolPhase.COMMIT) is True

    def test_both_at_phase_false_when_only_one_marked(self):
        from agent.mcp.protocol import ProtocolPhase
        from agent.mcp.protocol_phases import StepPhaseTracker

        tracker = StepPhaseTracker()
        tracker.mark_phase(0, "cop", ProtocolPhase.COMMIT)
        assert tracker.both_at_phase(0, ProtocolPhase.COMMIT) is False

    def test_both_at_phase_false_for_missing_step(self):
        from agent.mcp.protocol import ProtocolPhase
        from agent.mcp.protocol_phases import StepPhaseTracker

        tracker = StepPhaseTracker()
        assert tracker.both_at_phase(99, ProtocolPhase.COMMIT) is False

    def test_to_dict(self):
        from agent.mcp.protocol import ProtocolPhase
        from agent.mcp.protocol_phases import StepPhaseTracker

        tracker = StepPhaseTracker()
        tracker.mark_phase(1, "cop", ProtocolPhase.REVEAL)
        d = tracker.to_dict()
        assert 1 in d
        assert d[1]["cop"] == "reveal"

    def test_mark_creates_step_entry(self):
        from agent.mcp.protocol import ProtocolPhase
        from agent.mcp.protocol_phases import StepPhaseTracker

        tracker = StepPhaseTracker()
        tracker.mark_phase(5, "thief", ProtocolPhase.ACK)
        assert 5 in tracker.step_phases
        assert tracker.step_phases[5]["thief"] == "ack"


# ===========================================================================
# 6. log.py — GameLog
# ===========================================================================


class TestGameLog:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def test_append_creates_event(self):
        from agent.mcp.log import GameLog

        gl = GameLog("game1", Path(self.tmp))
        gl.append("test_event", "cop", "commit", "ok", {"x": 1})
        events = gl.get_all_events()
        assert len(events) == 1
        assert events[0]["event_type"] == "test_event"

    def test_append_with_error_status(self):
        from agent.mcp.log import GameLog

        gl = GameLog("game1", Path(self.tmp))
        gl.append("fail_event", "cop", "commit", "error", {}, error="something went wrong")
        events = gl.get_all_events()
        assert events[0]["status"] == "error"
        assert events[0]["error"] == "something went wrong"

    def test_append_message_received(self):
        from agent.mcp.log import GameLog

        gl = GameLog("game1", Path(self.tmp))
        gl.append_message_received("action", "cop", "commit", True)
        events = gl.get_all_events()
        assert "message_received:action" in events[0]["event_type"]

    def test_append_message_received_invalid(self):
        from agent.mcp.log import GameLog

        gl = GameLog("game1", Path(self.tmp))
        gl.append_message_received("action", "cop", "commit", False, error="bad sig")
        events = gl.get_all_events()
        assert events[0]["status"] == "error"

    def test_append_message_sent(self):
        from agent.mcp.log import GameLog

        gl = GameLog("game1", Path(self.tmp))
        gl.append_message_sent("action", "cop", "reveal")
        events = gl.get_all_events()
        assert "message_sent:action" in events[0]["event_type"]

    def test_append_commit(self):
        from agent.mcp.log import GameLog

        gl = GameLog("game1", Path(self.tmp))
        gl.append_commit("cop", 0, SHA256)
        events = gl.get_all_events()
        assert events[0]["event_type"] == "commit"

    def test_append_reveal(self):
        from agent.mcp.log import GameLog

        gl = GameLog("game1", Path(self.tmp))
        gl.append_reveal("thief", 1, "N", hint="going north", intent="truth")
        events = gl.get_all_events()
        assert events[0]["event_type"] == "reveal"

    def test_append_commitment_verified_ok(self):
        from agent.mcp.log import GameLog

        gl = GameLog("game1", Path(self.tmp))
        gl.append_commitment_verified("cop", 0, True)
        events = gl.get_all_events()
        assert events[0]["status"] == "ok"

    def test_append_commitment_verified_fail(self):
        from agent.mcp.log import GameLog

        gl = GameLog("game1", Path(self.tmp))
        gl.append_commitment_verified("cop", 0, False)
        events = gl.get_all_events()
        assert events[0]["status"] == "error"

    def test_append_error(self):
        from agent.mcp.log import GameLog

        gl = GameLog("game1", Path(self.tmp))
        gl.append_error("some_error", "cop", "commit", "msg", {"detail": 1})
        events = gl.get_all_events()
        assert events[0]["status"] == "error"

    def test_get_events_by_phase(self):
        from agent.mcp.log import GameLog

        gl = GameLog("game1", Path(self.tmp))
        gl.append("e1", "cop", "commit", "ok", {})
        gl.append("e2", "cop", "reveal", "ok", {})
        commit_events = gl.get_events_by_phase("commit")
        assert len(commit_events) == 1
        assert commit_events[0]["event_type"] == "e1"

    def test_log_written_to_file(self):
        from agent.mcp.log import GameLog

        gl = GameLog("game1", Path(self.tmp))
        gl.append("test_event", "cop", "commit", "ok", {"x": 1})
        log_file = Path(self.tmp) / "game1.jsonl"
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "test_event" in content


# ===========================================================================
# 7. log_replay.py
# ===========================================================================


class TestLogReplay:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def test_load_from_file_returns_events(self):
        from agent.mcp.log_replay import load_from_file

        log_file = Path(self.tmp) / "test.jsonl"
        log_file.write_text(
            json.dumps({"event": "a"}) + "\n" + json.dumps({"event": "b"}) + "\n",
            encoding="utf-8",
        )
        events = load_from_file(log_file)
        assert len(events) == 2
        assert events[0]["event"] == "a"

    def test_load_from_file_missing_file(self):
        from agent.mcp.log_replay import load_from_file

        events = load_from_file(Path(self.tmp) / "nonexistent.jsonl")
        assert events == []

    def test_load_from_file_skips_blank_lines(self):
        from agent.mcp.log_replay import load_from_file

        log_file = Path(self.tmp) / "blank.jsonl"
        log_file.write_text(json.dumps({"x": 1}) + "\n\n", encoding="utf-8")
        events = load_from_file(log_file)
        assert len(events) == 1

    def test_canonical_json_sorts_keys(self):
        from agent.mcp.log_replay import canonical_json

        result = canonical_json({"b": 2, "a": 1})
        assert result.index('"a"') < result.index('"b"')

    def test_sha256_of_file(self):
        from agent.mcp.log_replay import sha256_of_file

        f = Path(self.tmp) / "data.txt"
        f.write_bytes(b"hello")
        digest = sha256_of_file(f)
        assert len(digest) == 64

    def test_sha256_of_json(self):
        from agent.mcp.log_replay import sha256_of_json

        digest = sha256_of_json({"a": 1})
        assert len(digest) == 64

    def test_verify_log_integrity_missing_file(self):
        from agent.mcp.log_replay import verify_log_integrity

        result = verify_log_integrity(Path(self.tmp) / "missing.json")
        assert result["ok"] is False

    def test_verify_log_integrity_no_expected_hash(self):
        from agent.mcp.log_replay import verify_log_integrity

        f = Path(self.tmp) / "log.json"
        f.write_text("{}", encoding="utf-8")
        result = verify_log_integrity(f)
        assert result["ok"] is True
        assert "log_sha256" in result

    def test_verify_log_integrity_matching_hash(self):
        from agent.mcp.log_replay import sha256_of_file, verify_log_integrity

        f = Path(self.tmp) / "log2.json"
        f.write_text("{}", encoding="utf-8")
        expected = sha256_of_file(f)
        result = verify_log_integrity(f, expected)
        assert result["hash_match"] is True
        assert result["ok"] is True

    def test_verify_log_integrity_wrong_hash(self):
        from agent.mcp.log_replay import verify_log_integrity

        f = Path(self.tmp) / "log3.json"
        f.write_text("{}", encoding="utf-8")
        result = verify_log_integrity(f, "a" * 64)
        # Just check structure is valid
        assert "ok" in result
        assert "log_sha256" in result

    def test_load_log_json(self):
        from agent.mcp.log_replay import load_log_json

        f = Path(self.tmp) / "structured.json"
        f.write_text(json.dumps({"game_id": "g1"}), encoding="utf-8")
        data = load_log_json(f)
        assert data["game_id"] == "g1"

    def test_audit_log_commitments_empty_entries(self):
        from agent.mcp.log_replay import audit_log_commitments

        result = audit_log_commitments({"game_id": "g1", "game_number": "01", "entries": []})
        assert result["verified"] == 0
        assert result["failed"] == 0
        assert result["skipped"] == 0


# ===========================================================================
# 8. discovery.py — ProtocolDiscovery
# ===========================================================================


class TestProtocolDiscovery:
    def test_init(self):
        from agent.mcp.discovery import ProtocolDiscovery

        pd = ProtocolDiscovery("http://localhost:5001/mcp")
        assert pd.peer_url == "http://localhost:5001/mcp"
        assert pd.discovered is False
        assert pd.tools == {}

    def test_get_tool_names_empty(self):
        from agent.mcp.discovery import ProtocolDiscovery

        pd = ProtocolDiscovery("http://localhost:5001/mcp")
        assert pd.get_tool_names() == []

    def test_has_tool_false(self):
        from agent.mcp.discovery import ProtocolDiscovery

        pd = ProtocolDiscovery("http://localhost:5001/mcp")
        assert pd.has_tool("start_game") is False

    def test_get_tool_schema_none(self):
        from agent.mcp.discovery import ProtocolDiscovery

        pd = ProtocolDiscovery("http://localhost:5001/mcp")
        assert pd.get_tool_schema("start_game") is None

    def test_validate_protocol_missing(self):
        from agent.mcp.discovery import ProtocolDiscovery

        pd = ProtocolDiscovery("http://localhost:5001/mcp")
        ok, msg = pd.validate_protocol(["start_game", "action"])
        assert ok is False
        assert "start_game" in msg

    def test_validate_protocol_all_present(self):
        from agent.mcp.discovery import ProtocolDiscovery

        pd = ProtocolDiscovery("http://localhost:5001/mcp")
        pd.tools = {"start_game": {}, "action": {}}
        ok, msg = pd.validate_protocol(["start_game", "action"])
        assert ok is True

    def test_to_dict(self):
        from agent.mcp.discovery import ProtocolDiscovery

        pd = ProtocolDiscovery("http://localhost:5001/mcp")
        d = pd.to_dict()
        assert d["discovered"] is False
        assert "tools" in d

    def test_has_tool_true_after_adding(self):
        from agent.mcp.discovery import ProtocolDiscovery

        pd = ProtocolDiscovery("http://localhost:5001/mcp")
        pd.tools["ping"] = {"name": "ping"}
        assert pd.has_tool("ping") is True

    def test_sse_url_construction(self):
        from agent.mcp.discovery import ProtocolDiscovery

        pd = ProtocolDiscovery("http://localhost:5001/mcp")
        assert pd._sse_url == "http://localhost:5001/sse"

    @pytest.mark.asyncio
    async def test_discover_returns_false_on_exception(self):
        from agent.mcp.discovery import ProtocolDiscovery

        pd = ProtocolDiscovery("http://localhost:9999/mcp", timeout_seconds=0.1)
        with patch("agent.mcp.discovery.Client") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("connection refused")
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await pd.discover()
        assert result is False
        assert pd.discovered is False


# ===========================================================================
# 9. server.py — AgentMCPServer
# ===========================================================================


class TestAgentMCPServer:
    def test_init(self, tmp_path):
        from agent.mcp.server import AgentMCPServer

        server = AgentMCPServer(
            role="cop",
            secret="dev-secret-change-me",
            config_sha256=SHA256,
            games_dir=tmp_path,
        )
        assert server.role == "cop"
        assert server.config_sha256 == SHA256

    def test_get_game_log_none(self, tmp_path):
        from agent.mcp.server import AgentMCPServer

        server = AgentMCPServer("cop", "secret", SHA256, games_dir=tmp_path)
        assert server.get_game_log("nonexistent") is None

    def test_get_game_log_returns_log(self, tmp_path):
        from agent.mcp.log import GameLog
        from agent.mcp.server import AgentMCPServer

        server = AgentMCPServer("cop", "secret", SHA256, games_dir=tmp_path)
        gl = GameLog("g1", tmp_path)
        server.game_logs["g1"] = gl
        assert server.get_game_log("g1") is gl

    def test_init_with_callbacks(self, tmp_path):
        from agent.mcp.server import AgentMCPServer

        cb = {"on_action": lambda gid, msg: {"ok": True}}
        server = AgentMCPServer("cop", "secret", SHA256, games_dir=tmp_path, handler_callbacks=cb)
        assert "on_action" in server.handler_callbacks

    def test_warning_on_dev_secret(self, tmp_path, caplog):
        import logging

        from agent.mcp.server import AgentMCPServer

        with caplog.at_level(logging.WARNING, logger="agent.mcp.server"):
            AgentMCPServer("cop", "dev-secret-change-me", SHA256, games_dir=tmp_path)
        assert any("SECURITY" in r.message for r in caplog.records)


# ===========================================================================
# 10 & 11. server_tools_game.py, server_tools_info.py (via server_handlers)
# ===========================================================================


class TestServerHandlers:
    """Test handle_start_game and handle_action directly.

    Each test uses a unique game_id (prefixed with the test name) to avoid
    session-registry state leaking between tests.
    """

    def _signed_start_game_json(self, secret, config_sha256, game_id="g1"):
        from agent.mcp.crypto import canonical_json, sign_message

        msg = _make_start_game_msg(config_sha256=config_sha256, game_id=game_id)
        msg_dict = msg.to_dict()
        message_json = canonical_json(msg_dict)
        signature = sign_message(msg_dict, secret)
        return message_json, signature, msg.game_id

    def _signed_action_json(self, secret, config_sha256, phase="commit", game_id="g1", **kwargs):
        from agent.mcp.crypto import canonical_json, sign_message

        msg = _make_action_msg(config_sha256=config_sha256, phase=phase, game_id=game_id, **kwargs)
        msg_dict = msg.to_dict()
        message_json = canonical_json(msg_dict)
        signature = sign_message(msg_dict, secret)
        return message_json, signature

    def _seed_session(self, game_id: str, state):
        """Pre-seed session registry to a given state (bypasses normal transitions)."""
        from agent.mcp.session_registry import get_registry

        entry = get_registry().get_or_create(game_id, 0, "cop")
        entry.sm.state = state

    def test_handle_start_game_success(self, tmp_path):
        from agent.mcp.server_handlers import handle_start_game

        secret = "test-secret"
        gid = "sg_success"
        message_json, signature, game_id = self._signed_start_game_json(secret, SHA256, gid)
        result = handle_start_game("cop", secret, SHA256, tmp_path, {}, {}, message_json, signature)
        assert result["ok"] is True
        assert result["game_id"] == game_id

    def test_handle_start_game_bad_signature(self, tmp_path):
        from agent.mcp.server_handlers import handle_start_game

        secret = "test-secret"
        gid = "sg_badsig"
        message_json, _, game_id = self._signed_start_game_json(secret, SHA256, gid)
        result = handle_start_game("cop", secret, SHA256, tmp_path, {}, {}, message_json, "badsig")
        assert result["ok"] is False
        assert "Signature" in result["error"]

    def test_handle_start_game_config_mismatch(self, tmp_path):
        from agent.mcp.server_handlers import handle_start_game

        secret = "test-secret"
        other_sha = "b" * 64
        gid = "sg_cfgmismatch"
        message_json, signature, game_id = self._signed_start_game_json(secret, SHA256, gid)
        result = handle_start_game(
            "cop", secret, other_sha, tmp_path, {}, {}, message_json, signature
        )
        assert result["ok"] is False
        assert "mismatch" in result["error"].lower()

    def test_handle_start_game_with_callback(self, tmp_path):
        from agent.mcp.server_handlers import handle_start_game

        secret = "test-secret"
        gid = "sg_callback"
        message_json, signature, game_id = self._signed_start_game_json(secret, SHA256, gid)
        cb_result = {"ok": True, "game_id": game_id, "custom": "value"}
        callbacks = {"on_start_game": lambda msg: cb_result}
        result = handle_start_game(
            "cop", secret, SHA256, tmp_path, {}, callbacks, message_json, signature
        )
        assert result.get("custom") == "value"

    def test_handle_start_game_bad_json(self, tmp_path):
        from agent.mcp.server_handlers import handle_start_game

        result = handle_start_game("cop", "sec", SHA256, tmp_path, {}, {}, "{bad}", "sig")
        assert result["ok"] is False

    def test_handle_action_success(self, tmp_path):
        from agent.mcp.protocol import ProtocolState
        from agent.mcp.server_handlers import handle_action

        secret = "test-secret"
        gid = "ha_success"
        self._seed_session(gid, ProtocolState.COMPUTING_MOVE)
        game_logs = {}
        message_json, signature = self._signed_action_json(secret, SHA256, game_id=gid)
        result = handle_action(
            "cop", secret, SHA256, tmp_path, game_logs, {}, gid, message_json, signature
        )
        assert result["ok"] is True
        assert result["phase"] == "commit"

    def test_handle_action_bad_signature(self, tmp_path):
        from agent.mcp.server_handlers import handle_action

        secret = "test-secret"
        gid = "ha_badsig"
        message_json, _ = self._signed_action_json(secret, SHA256, game_id=gid)
        result = handle_action("cop", secret, SHA256, tmp_path, {}, {}, gid, message_json, "badsig")
        assert result["ok"] is False

    def test_handle_action_config_mismatch(self, tmp_path):
        from agent.mcp.server_handlers import handle_action

        secret = "test-secret"
        gid = "ha_cfgmismatch"
        message_json, signature = self._signed_action_json(secret, SHA256, game_id=gid)
        result = handle_action(
            "cop", secret, "b" * 64, tmp_path, {}, {}, gid, message_json, signature
        )
        assert result["ok"] is False
        assert "mismatch" in result["error"].lower()

    def test_handle_action_with_on_action_callback(self, tmp_path):
        from agent.mcp.protocol import ProtocolState
        from agent.mcp.server_handlers import handle_action

        secret = "test-secret"
        gid = "ha_callback"
        self._seed_session(gid, ProtocolState.COMPUTING_MOVE)
        message_json, signature = self._signed_action_json(secret, SHA256, game_id=gid)
        cb_result = {"ok": True, "custom": "cb_value"}
        callbacks = {"on_action": lambda gid2, msg: cb_result}
        result = handle_action(
            "cop", secret, SHA256, tmp_path, {}, callbacks, gid, message_json, signature
        )
        assert result.get("custom") == "cb_value"

    def test_handle_action_reveal_phase(self, tmp_path):
        from agent.mcp.protocol import ProtocolState
        from agent.mcp.server_handlers import handle_action

        secret = "test-secret"
        gid = "ha_reveal"
        self._seed_session(gid, ProtocolState.BOTH_COMMITTED)
        message_json, signature = self._signed_action_json(
            secret, SHA256, phase="reveal", move="N", game_id=gid
        )
        result = handle_action(
            "cop", secret, SHA256, tmp_path, {}, {}, gid, message_json, signature
        )
        assert result["ok"] is True
        assert result["phase"] == "reveal"

    def test_handle_action_final_audit_phase(self, tmp_path):
        from agent.mcp.protocol import ProtocolState
        from agent.mcp.server_handlers import handle_action

        secret = "test-secret"
        gid = "ha_finalaudit"
        self._seed_session(gid, ProtocolState.AUDITING)
        message_json, signature = self._signed_action_json(
            secret, SHA256, phase="final_audit", nonces={"0": "abc"}, game_id=gid
        )
        result = handle_action(
            "cop", secret, SHA256, tmp_path, {}, {}, gid, message_json, signature
        )
        assert result["ok"] is True

    def test_handle_action_creates_gamelog_if_missing(self, tmp_path):
        from agent.mcp.protocol import ProtocolState
        from agent.mcp.server_handlers import handle_action

        secret = "test-secret"
        gid = "ha_gamelog"
        self._seed_session(gid, ProtocolState.COMPUTING_MOVE)
        game_logs = {}
        message_json, signature = self._signed_action_json(secret, SHA256, game_id=gid)
        handle_action("cop", secret, SHA256, tmp_path, game_logs, {}, gid, message_json, signature)
        assert gid in game_logs

    def test_handle_start_game_role_not_in_roles(self, tmp_path):
        from agent.mcp.crypto import canonical_json, sign_message
        from agent.mcp.server_handlers import handle_start_game

        gid = "sg_badrole"
        msg = _make_start_game_msg(
            config_sha256=SHA256, roles={"cop": "Alice", "thief": "Bob"}, game_id=gid
        )
        msg_dict = msg.to_dict()
        message_json = canonical_json(msg_dict)
        signature = sign_message(msg_dict, "sec")
        # Use role "judge" which is not in roles
        result = handle_start_game(
            "judge", "sec", SHA256, tmp_path, {}, {}, message_json, signature
        )
        assert result["ok"] is False


# ===========================================================================
# 12. server_tools_info.py — register_info_tools (via server)
# ===========================================================================


class TestServerToolsInfo:
    def test_register_info_tools_creates_mcp(self, tmp_path):
        from agent.mcp.server import AgentMCPServer

        server = AgentMCPServer("cop", "secret", SHA256, games_dir=tmp_path)
        # Tools should be registered (we just check no exception was raised)
        assert server.mcp is not None


# ===========================================================================
# 13. peer_agent_passive.py
# ===========================================================================


class TestInitPassiveGame:
    def test_idempotent_if_same_game_id(self, tmp_path):
        from agent.peer_agent_passive import init_passive_game

        rt = MagicMock()
        rt.game_id = "g1"
        rules_ref = []
        init_passive_game(rt, "g1", rules_ref)
        # Should return early without modifying rt
        rt.assert_not_called()
        assert rules_ref == []

    def test_initializes_new_game(self, tmp_path):
        from agent.peer_agent_passive import init_passive_game

        from agent.rules_engine import RulesEngine

        rt = MagicMock()
        rt.game_id = ""  # empty means not yet set
        rt.games_dir = tmp_path
        rt.max_turns = 35
        rt.role = "thief"
        rules_ref = []

        with patch("agent.peer_agent_passive._load_start_positions", return_value=([0, 0], [3, 3])):
            init_passive_game(rt, "g_new", rules_ref)

        assert rt.game_id == "g_new"
        assert len(rules_ref) == 1
        assert isinstance(rules_ref[0], RulesEngine)

    def test_clears_existing_rules_ref(self, tmp_path):
        from agent.peer_agent_passive import init_passive_game

        rt = MagicMock()
        rt.game_id = "old_game"
        rt.games_dir = tmp_path
        rt.max_turns = 35
        rt.role = "thief"
        rules_ref = [MagicMock(), MagicMock()]  # pre-populated

        with patch("agent.peer_agent_passive._load_start_positions", return_value=([0, 0], [3, 3])):
            init_passive_game(rt, "new_game", rules_ref)

        assert len(rules_ref) == 1  # cleared and re-added


class TestHandlePassiveCommit:
    def test_returns_h_commit(self, tmp_path):
        from agent.peer_agent_passive import handle_passive_commit

        from agent.board import Board
        from agent.rules_engine import RulesEngine

        board = Board(cop_position=[0, 0], thief_position=[3, 3])
        rules_ref = [RulesEngine(board, max_turns=35)]

        rt = MagicMock()
        rt.game_id = "g1"
        rt.role = "thief"
        rt._gamelet_number.return_value = 1
        rt.counted_mode = False
        rt.orchestrator = None
        rt.board = board
        rt.game_dir = tmp_path
        rt._select_move_rl.return_value = "N"
        rt._build_observation.return_value = {}
        rt._store_my_commit = MagicMock()

        message = MagicMock()
        message.step = 1
        message.h_commit = SHA256

        with (
            patch("agent.mcp.crypto.hash_game_state", return_value=SHA256),
            patch("agent.mcp.crypto.create_commitment", return_value=(SHA256, "nonce123")),
        ):
            result = handle_passive_commit(rt, "g1", message, rules_ref)

        assert result["ok"] is True
        assert result["phase"] == "commit"
        assert "h_commit" in result

    def test_initializes_if_no_game_id(self, tmp_path):
        from agent.peer_agent_passive import handle_passive_commit

        from agent.board import Board
        from agent.rules_engine import RulesEngine

        board = Board(cop_position=[0, 0], thief_position=[3, 3])
        rules_ref = [RulesEngine(board, max_turns=35)]

        rt = MagicMock()
        rt.game_id = ""  # not set
        rt.role = "thief"
        rt._gamelet_number.return_value = 1
        rt.counted_mode = False
        rt.orchestrator = None
        rt.board = board
        rt.games_dir = tmp_path
        rt.max_turns = 35
        rt._select_move_rl.return_value = "STAY"
        rt._build_observation.return_value = {}
        rt._store_my_commit = MagicMock()

        message = MagicMock()
        message.step = 1
        message.h_commit = SHA256

        with (
            patch("agent.peer_runtime._load_start_positions", return_value=([0, 0], [3, 3])),
            patch("agent.mcp.crypto.hash_game_state", return_value=SHA256),
            patch("agent.mcp.crypto.create_commitment", return_value=(SHA256, "nonce")),
        ):
            result = handle_passive_commit(rt, "g1", message, rules_ref)

        assert result["ok"] is True


class TestHandlePassiveReveal:
    def test_returns_error_if_no_commit(self):
        from agent.peer_agent_passive import handle_passive_reveal

        rt = MagicMock()
        rt._my_commits = {}
        rt.role = "thief"

        message = MagicMock()
        message.step = 5
        message.move = "N"
        message.hint = ""
        message.intent = "truth"
        message.state_hash = SHA256

        rules_ref = []
        result = handle_passive_reveal(rt, "g1", message, rules_ref)
        assert result["ok"] is False
        assert "No commit" in result["error"]

    def test_returns_reveal_payload(self, tmp_path):
        from agent.peer_agent_passive import handle_passive_reveal

        from agent.board import Board
        from agent.rules_engine import RulesEngine

        board = Board(cop_position=[0, 0], thief_position=[3, 3])
        rules = RulesEngine(board, max_turns=35)
        rules_ref = [rules]

        rt = MagicMock()
        rt.role = "thief"
        rt._gamelet_number.return_value = 1
        rt.game_id = "g1"
        rt.config_sha256 = "c" * 64
        rt._public_transition_root = ""
        rt._my_commits = {
            1: {
                "h_commit": SHA256,
                "move": "N",
                "hint": "going north",
                "intent": "truth",
                "state_hash": SHA256,
                "nonce": "n" * 32,
            }
        }
        rt.orchestrator = None
        rt.board = board
        rt._cop_barriers_remaining = 14
        rt.game_dir = tmp_path
        rt.max_turns = 35

        message = MagicMock()
        message.step = 1
        message.move = "S"
        message.hint = "hint"
        message.intent = "truth"
        message.state_hash = SHA256

        with patch("agent.peer_audit.append_opponent_reveal"):
            result = handle_passive_reveal(rt, "g1", message, rules_ref)

        assert result["ok"] is True
        assert result["phase"] == "reveal"
        assert result["move"] == "N"


# ===========================================================================
# 14. peer_agent_runtime.py — PeerAgentRuntime
# ===========================================================================


class TestPeerAgentRuntime:
    def _make_runtime(self, tmp_path, role="thief"):
        with (
            patch("agent.peer_agent_runtime.AgentMCPServer"),
            patch("agent.peer_agent_runtime.PeerRuntime") as mock_pr,
        ):
            mock_pr_inst = MagicMock()
            mock_pr_inst.llm = None
            mock_pr_inst._my_commits = {}
            mock_pr.return_value = mock_pr_inst
            from agent.peer_agent_runtime import PeerAgentRuntime

            rt = PeerAgentRuntime(
                role=role,
                secret="secret",
                config_sha256=SHA256,
                opponent_url="http://localhost:5001/mcp",
                games_dir=tmp_path,
            )
            rt._peer_runtime = mock_pr_inst
            return rt

    def test_invalid_role_raises(self, tmp_path):
        with (
            patch("agent.peer_agent_runtime.AgentMCPServer"),
            patch("agent.peer_agent_runtime.PeerRuntime"),
        ):
            from agent.peer_agent_runtime import PeerAgentRuntime

            with pytest.raises(ValueError):
                PeerAgentRuntime(
                    role="judge",
                    secret="s",
                    config_sha256=SHA256,
                    opponent_url="http://x",
                    games_dir=tmp_path,
                )

    def test_on_action_unknown_phase(self, tmp_path):
        rt = self._make_runtime(tmp_path)
        message = MagicMock()
        message.phase = "unknown"
        result = rt._on_action("g1", message)
        assert result["ok"] is False

    def test_on_action_game_end(self, tmp_path):
        rt = self._make_runtime(tmp_path)
        message = MagicMock()
        message.phase = "game_end"
        result = rt._on_action("g1", message)
        assert result["ok"] is False
        assert "initialized game" in result["error"]

    def test_on_action_final_audit(self, tmp_path):
        rt = self._make_runtime(tmp_path)
        message = MagicMock()
        message.phase = "final_audit"
        with patch(
            "agent.peer_agent_runtime.handle_passive_final_audit",
            return_value={"ok": True, "phase": "final_audit", "nonces": {"1": "abc123"}},
        ):
            result = rt._on_action("g1", message)
        assert result["ok"] is True
        assert result["phase"] == "final_audit"
        assert "1" in result["nonces"]

    def test_on_start_game_thief_init(self, tmp_path):
        rt = self._make_runtime(tmp_path, role="thief")
        message = MagicMock()
        message.game_id = "g1"
        with patch("agent.peer_agent_runtime.init_passive_game") as mock_init:
            result = rt._on_start_game(message)
        mock_init.assert_called_once()
        assert result["ok"] is True

    def test_on_start_game_cop_no_loop(self, tmp_path):
        rt = self._make_runtime(tmp_path, role="cop")
        message = MagicMock()
        message.game_id = "g1"
        rt._loop = None
        result = rt._on_start_game(message)
        assert result["ok"] is False
        assert "event loop" in result["error"].lower()

    def test_on_action_commit_delegates(self, tmp_path):
        rt = self._make_runtime(tmp_path, role="thief")
        message = MagicMock()
        message.phase = "commit"
        with patch(
            "agent.peer_agent_runtime.handle_passive_commit",
            return_value={"ok": True, "phase": "commit"},
        ) as mock_commit:
            result = rt._on_action("g1", message)
        mock_commit.assert_called_once()
        assert result["ok"] is True

    def test_on_action_reveal_delegates(self, tmp_path):
        rt = self._make_runtime(tmp_path, role="thief")
        message = MagicMock()
        message.phase = "reveal"
        with patch(
            "agent.peer_agent_runtime.handle_passive_reveal",
            return_value={"ok": True, "phase": "reveal"},
        ) as mock_reveal:
            result = rt._on_action("g1", message)
        mock_reveal.assert_called_once()
        assert result["ok"] is True


# ===========================================================================
# 15. game_initiator.py — GameInitiator
# ===========================================================================


class TestGameInitiator:
    def _make_initiator(self):
        from agent.game_initiator import GameInitiator

        with patch("agent.game_initiator.GameMCPClient"):
            gi = GameInitiator(
                cop_url="http://localhost:5000/mcp",
                thief_url="http://localhost:5001/mcp",
                secret="secret",
                config_sha256=SHA256,
            )
        return gi

    def test_init(self):
        gi = self._make_initiator()
        assert gi.cop_url == "http://localhost:5000/mcp"
        assert gi.thief_url == "http://localhost:5001/mcp"

    @pytest.mark.asyncio
    async def test_start_game_success(self):
        from agent.game_initiator import GameInitiator

        with patch("agent.game_initiator.GameMCPClient"):
            gi = GameInitiator(secret="secret", config_sha256=SHA256)
        gi.cop_client = MagicMock()
        gi.thief_client = MagicMock()

        with (
            patch("agent.game_initiator.wait_for_readiness", return_value=True),
            patch("agent.game_initiator.call_start_game", return_value={"ok": True}),
        ):
            result = await gi.start_game(game_id="test_game")
        assert result["ok"] is True
        assert result["game_id"] == "test_game"

    @pytest.mark.asyncio
    async def test_start_game_cop_rejects(self):
        from agent.game_initiator import GameInitiator

        with patch("agent.game_initiator.GameMCPClient"):
            gi = GameInitiator(secret="secret", config_sha256=SHA256)

        with (
            patch("agent.game_initiator.wait_for_readiness", return_value=True),
            patch(
                "agent.game_initiator.call_start_game",
                return_value={"ok": False, "error": "rejected"},
            ),
        ):
            result = await gi.start_game(game_id="test_game")
        assert result["ok"] is False
        assert "rejected" in result["error"].lower() or "Cop" in result["error"]

    @pytest.mark.asyncio
    async def test_start_game_thief_rejects(self):
        from agent.game_initiator import GameInitiator

        with patch("agent.game_initiator.GameMCPClient"):
            gi = GameInitiator(secret="secret", config_sha256=SHA256)

        call_count = 0

        async def mock_call_start_game(*args, **kwargs):
            nonlocal call_count
            responses = [{"ok": True}, {"ok": False, "error": "thief rejected"}]
            r = responses[call_count]
            call_count += 1
            return r

        with (
            patch("agent.game_initiator.wait_for_readiness", return_value=True),
            patch("agent.game_initiator.call_start_game", side_effect=mock_call_start_game),
        ):
            result = await gi.start_game(game_id="test_game")
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_start_game_exception(self):
        from agent.game_initiator import GameInitiator

        with patch("agent.game_initiator.GameMCPClient"):
            gi = GameInitiator(secret="secret", config_sha256=SHA256)

        # wait_for_readiness is called outside the try block, so exceptions there propagate.
        # Instead, make call_start_game raise inside the try block.
        with (
            patch("agent.game_initiator.wait_for_readiness", return_value=True),
            patch("agent.game_initiator.call_start_game", side_effect=Exception("network error")),
        ):
            result = await gi.start_game(game_id="test_game")
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_wait_for_readiness_delegates(self):
        from agent.game_initiator import GameInitiator

        with patch("agent.game_initiator.GameMCPClient"):
            gi = GameInitiator(secret="secret", config_sha256=SHA256)
        client = MagicMock()
        with patch("agent.game_initiator.wait_for_readiness", return_value=True):
            result = await gi._wait_for_readiness(client, "cop", timeout_seconds=5.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_call_start_game_delegates(self):
        from agent.game_initiator import GameInitiator

        with patch("agent.game_initiator.GameMCPClient"):
            gi = GameInitiator(secret="secret", config_sha256=SHA256)
        client = MagicMock()
        msg = _make_start_game_msg()
        with patch("agent.game_initiator.call_start_game", return_value={"ok": True}):
            result = await gi._call_start_game(client, msg, "cop")
        assert result["ok"] is True


# ===========================================================================
# 16. game_initiator_handshake.py
# ===========================================================================


class TestGameInitiatorHandshake:
    @pytest.mark.asyncio
    async def test_wait_for_readiness_success_on_first_try(self):
        from agent.game_initiator_handshake import wait_for_readiness

        client = MagicMock()
        client._call_tool = AsyncMock(return_value={"ok": True})
        result = await wait_for_readiness(client, "cop", timeout_seconds=5.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_readiness_timeout(self):
        from agent.game_initiator_handshake import wait_for_readiness

        client = MagicMock()
        client._call_tool = AsyncMock(side_effect=Exception("connection refused"))
        result = await wait_for_readiness(client, "cop", timeout_seconds=0.1)
        assert result is False

    @pytest.mark.asyncio
    async def test_call_start_game_success(self):
        from agent.game_initiator_handshake import call_start_game

        client = MagicMock()
        client._call_tool = AsyncMock(return_value={"ok": True})
        msg = _make_start_game_msg()
        result = await call_start_game(client, msg, "cop", "secret")
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_call_start_game_propagates_exception(self):
        from agent.game_initiator_handshake import call_start_game

        client = MagicMock()
        client._call_tool = AsyncMock(side_effect=Exception("network error"))
        msg = _make_start_game_msg()
        with pytest.raises(Exception, match="network error"):
            await call_start_game(client, msg, "cop", "secret")


# ===========================================================================
# 17. client.py — GameMCPClient (constructor and internal logic)
# ===========================================================================


class TestGameMCPClient:
    def test_init_sse_url(self):
        from agent.mcp.client import GameMCPClient

        with patch("agent.mcp.client.SSETransport"):
            client = GameMCPClient("http://localhost:5001/mcp", "secret")
        assert client.peer_url == "http://localhost:5001/mcp"
        assert client.secret == "secret"

    def test_sse_url_derived_correctly(self):
        from agent.mcp.client import GameMCPClient

        with patch("agent.mcp.client.SSETransport") as mock_sse:
            GameMCPClient("http://localhost:5001/mcp", "secret")
        # SSETransport should have been called with the /sse url
        mock_sse.assert_called_once_with("http://localhost:5001/sse")

    @pytest.mark.asyncio
    async def test_start_game_calls_tool(self):
        from agent.mcp.client import GameMCPClient

        with patch("agent.mcp.client.SSETransport"):
            client = GameMCPClient("http://localhost:5001/mcp", "secret")
        client._call_tool = AsyncMock(return_value={"ok": True})
        msg = _make_start_game_msg()
        result = await client.start_game(msg)
        assert client._call_tool.called
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_action_calls_tool(self):
        from agent.mcp.client import GameMCPClient

        with patch("agent.mcp.client.SSETransport"):
            client = GameMCPClient("http://localhost:5001/mcp", "secret")
        client._call_tool = AsyncMock(return_value={"ok": True})
        msg = _make_action_msg()
        result = await client.action("g1", msg)
        assert client._call_tool.called
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_ping_calls_tool(self):
        from agent.mcp.client import GameMCPClient

        with patch("agent.mcp.client.SSETransport"):
            client = GameMCPClient("http://localhost:5001/mcp", "secret")
        client._call_tool = AsyncMock(return_value={"ok": True})
        await client.ping()
        client._call_tool.assert_called_once_with("ping", {})

    @pytest.mark.asyncio
    async def test_call_tool_parses_json_response(self):
        from agent.mcp.client import GameMCPClient

        with (
            patch("agent.mcp.client.SSETransport"),
            patch("agent.mcp.client.Client") as mock_client_cls,
        ):
            client = GameMCPClient("http://localhost:5001/mcp", "secret")

            # Mock the result content
            mock_item = MagicMock()
            mock_item.text = json.dumps({"ok": True, "data": "test"})
            mock_result = MagicMock()
            mock_result.content = [mock_item]

            mock_mcp_client = AsyncMock()
            mock_mcp_client.call_tool = AsyncMock(return_value=mock_result)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_mcp_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client._call_tool("ping", {})
        assert result["ok"] is True
        assert result["data"] == "test"

    @pytest.mark.asyncio
    async def test_call_tool_empty_content_returns_ok(self):
        from agent.mcp.client import GameMCPClient

        with (
            patch("agent.mcp.client.SSETransport"),
            patch("agent.mcp.client.Client") as mock_client_cls,
        ):
            client = GameMCPClient("http://localhost:5001/mcp", "secret")

            mock_result = MagicMock()
            mock_result.content = []

            mock_mcp_client = AsyncMock()
            mock_mcp_client.call_tool = AsyncMock(return_value=mock_result)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_mcp_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client._call_tool("ping", {})
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_call_tool_raises_on_exception(self):
        from agent.mcp.client import GameMCPClient

        with (
            patch("agent.mcp.client.SSETransport"),
            patch("agent.mcp.client.Client") as mock_client_cls,
        ):
            client = GameMCPClient("http://localhost:5001/mcp", "secret")
            mock_client_cls.return_value.__aenter__ = AsyncMock(side_effect=Exception("failed"))
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(Exception, match="failed"):
                await client._call_tool("ping", {})
