"""Tests that the replay auditor verifies real logs and detects tampering."""

import json
from pathlib import Path

from cop_worker.crypto import create_commitment
from cop_worker.mcp.log_replay import (
    audit_log_commitments,
    sha256_of_file,
    verify_log_integrity,
)


def _make_log(tmp_path: Path, game_id: str, entries: list[dict]) -> Path:
    data = {"game_id": game_id, "game_number": "g01", "entries": entries}
    p = tmp_path / f"log_{game_id}_g01.json"
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return p


def _make_entry(
    step: int,
    cop_h: str,
    thief_h: str,
    cop_move="N",
    thief_move="S",
    cop_nonce="cn",
    thief_nonce="tn",
    state_hash="sh",
) -> dict:
    return {
        "step": step,
        "cop_h_commit": cop_h,
        "thief_h_commit": thief_h,
        "cop_move": cop_move,
        "thief_move": thief_move,
        "cop_state_hash": state_hash,
        "thief_state_hash": state_hash,
        "cop_nonce": cop_nonce,
        "thief_nonce": thief_nonce,
        "cop_hint": "hint",
        "cop_intent": "truth",
        "thief_hint": "hint",
        "thief_intent": "truth",
    }


class TestLogIntegrity:
    def test_valid_log_passes_integrity(self, tmp_path):
        p = _make_log(tmp_path, "g001", [])
        sha = sha256_of_file(p)
        result = verify_log_integrity(p, expected_hash=sha)
        assert result["ok"] is True
        assert result["hash_match"] is True

    def test_tampered_log_fails_integrity(self, tmp_path):
        p = _make_log(tmp_path, "g002", [])
        original_sha = sha256_of_file(p)
        # Tamper the file
        p.write_text(p.read_text() + " ", encoding="utf-8")
        result = verify_log_integrity(p, expected_hash=original_sha)
        assert result["ok"] is False
        assert result["hash_match"] is False
        assert "tampered" in result["details"]

    def test_missing_log_returns_not_ok(self, tmp_path):
        result = verify_log_integrity(tmp_path / "nonexistent.json")
        assert result["ok"] is False

    def test_without_expected_hash_still_returns_sha(self, tmp_path):
        p = _make_log(tmp_path, "g003", [])
        result = verify_log_integrity(p)
        assert "log_sha256" in result
        assert len(result["log_sha256"]) == 64


class TestAuditLogCommitments:
    def _make_real_commit(
        self, game_id, step, role, move, state_hash="sh", hint="hint", intent="truth", gamelet=1
    ):
        h, nonce = create_commitment(
            game_id=game_id,
            step=step,
            role=role,
            state_hash=state_hash,
            move=move,
            hint=hint,
            intent=intent,
            gamelet=gamelet,
        )
        return h, nonce

    def test_valid_log_all_ok(self, tmp_path):
        game_id = "audit_test_001"
        cop_h, cop_nonce = self._make_real_commit(game_id, 1, "cop", "N")
        thief_h, thief_nonce = self._make_real_commit(game_id, 1, "thief", "S")

        entry = _make_entry(
            1,
            cop_h,
            thief_h,
            cop_move="N",
            thief_move="S",
            cop_nonce=cop_nonce,
            thief_nonce=thief_nonce,
        )
        log_data = {"game_id": game_id, "game_number": "g01", "entries": [entry]}

        result = audit_log_commitments(log_data)
        assert result["ok"] is True
        assert result["verified"] == 2
        assert result["failed"] == 0

    def test_tampered_move_fails(self, tmp_path):
        game_id = "audit_test_002"
        cop_h, cop_nonce = self._make_real_commit(game_id, 1, "cop", "N")
        thief_h, thief_nonce = self._make_real_commit(game_id, 1, "thief", "S")

        entry = _make_entry(
            1,
            cop_h,
            thief_h,
            cop_move="W",  # tampered: committed N but reveals W
            thief_move="S",
            cop_nonce=cop_nonce,
            thief_nonce=thief_nonce,
        )
        log_data = {"game_id": game_id, "game_number": "g01", "entries": [entry]}

        result = audit_log_commitments(log_data)
        assert result["ok"] is False
        assert result["failed"] >= 1

    def test_missing_nonce_skipped(self, tmp_path):
        game_id = "audit_test_003"
        cop_h, cop_nonce = self._make_real_commit(game_id, 1, "cop", "N")
        entry = {
            "step": 1,
            "cop_h_commit": cop_h,
            "cop_move": "N",
            "cop_state_hash": "sh",
            # cop_nonce missing → skipped
        }
        log_data = {"game_id": game_id, "game_number": "g01", "entries": [entry]}
        result = audit_log_commitments(log_data)
        assert result["skipped"] >= 1
        assert result["failed"] == 0

    def test_empty_log_not_ok(self):
        # An empty log has 0 verified entries; replay must verify at least one commitment.
        result = audit_log_commitments({"game_id": "empty", "game_number": "g01", "entries": []})
        assert result["ok"] is False
        assert result["verified"] == 0
        assert result["failed"] == 0
