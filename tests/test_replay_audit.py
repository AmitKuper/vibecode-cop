"""Tests that the replay auditor verifies real logs and detects tampering."""

import json
from pathlib import Path

from cop_worker.mcp.log_replay import sha256_of_file, verify_log_integrity


def _make_log(tmp_path: Path, game_id: str, entries: list[dict]) -> Path:
    data = {"game_id": game_id, "game_number": "g01", "entries": entries}
    p = tmp_path / f"log_{game_id}_g01.json"
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return p


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
