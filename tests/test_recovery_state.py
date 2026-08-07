"""Tests for RecoveryState — durable process-restart persistence."""

import json
import time
from pathlib import Path

import pytest

from cop_worker.reliability.recovery_state import RecoveryState, RecoveryStore


@pytest.fixture
def store_path(tmp_path):
    return str(tmp_path / "recovery.json")


@pytest.fixture
def store(store_path):
    return RecoveryStore(store_path)


def _make_state(**overrides) -> RecoveryState:
    defaults = {
        "game_uid": "game-001",
        "session_id": "sess-xyz",
        "role": "cop",
        "sm_state": "STEP_VERIFIED",
        "expected_step": 5,
        "last_accepted_commit_step": 4,
        "transcript_root": "/tmp/transcripts/game-001",
        "idempotency_journal": {"key1": "val1"},
        "pending_request_id": "req-abc",
        "local_commitments": {"1": "h_abc", "2": "h_def"},
        "local_nonces": {"1": "nonce-secret-1", "2": "nonce-secret-2"},
        "report_delivered": False,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    defaults.update(overrides)
    return RecoveryState(**defaults)


class TestSaveAndLoad:
    def test_round_trip(self, store):
        state = _make_state()
        store.save(state)
        loaded = store.load()
        assert loaded is not None
        assert loaded.game_uid == state.game_uid
        assert loaded.session_id == state.session_id
        assert loaded.role == state.role
        assert loaded.sm_state == state.sm_state
        assert loaded.expected_step == state.expected_step
        assert loaded.local_commitments == state.local_commitments
        assert loaded.local_nonces == state.local_nonces
        assert loaded.schema_version == "1.0"

    def test_load_returns_none_if_missing(self, store):
        result = store.load()
        assert result is None

    def test_overwrites_previous(self, store):
        state1 = _make_state(expected_step=3)
        state2 = _make_state(expected_step=7)
        store.save(state1)
        store.save(state2)
        loaded = store.load()
        assert loaded.expected_step == 7


class TestClear:
    def test_clear_removes_file(self, store, store_path):
        store.save(_make_state())
        assert Path(store_path).exists()
        store.clear()
        assert not Path(store_path).exists()

    def test_clear_idempotent_when_no_file(self, store):
        # Should not raise
        store.clear()
        store.clear()


class TestAtomicSave:
    def test_no_tmp_file_after_save(self, store, store_path):
        store.save(_make_state())
        tmp_path = store_path + ".tmp"
        assert not Path(tmp_path).exists()

    def test_main_file_valid_json_after_save(self, store, store_path):
        store.save(_make_state())
        data = json.loads(Path(store_path).read_text())
        assert "game_uid" in data
        assert "local_nonces" in data


class TestNonces:
    def test_nonces_present_in_saved_state(self, store, store_path):
        nonces = {"1": "secret-abc", "3": "secret-xyz"}
        store.save(_make_state(local_nonces=nonces))
        data = json.loads(Path(store_path).read_text())
        assert data["local_nonces"] == nonces

    def test_nonces_survive_round_trip(self, store):
        nonces = {"2": "n2", "4": "n4"}
        store.save(_make_state(local_nonces=nonces))
        loaded = store.load()
        assert loaded.local_nonces == nonces


class TestCanonicalBytes:
    def test_deterministic_output(self):
        state = _make_state()
        b1 = state.canonical_bytes()
        b2 = state.canonical_bytes()
        assert b1 == b2

    def test_different_states_differ(self):
        s1 = _make_state(expected_step=1)
        s2 = _make_state(expected_step=2)
        assert s1.canonical_bytes() != s2.canonical_bytes()
