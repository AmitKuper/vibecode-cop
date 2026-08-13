"""Appendix-F scoring reads OUR real token spend from the ledger (opponent stays 0)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from cop_worker.language import token_ledger

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from ref3_artifacts import score_series  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_ledger():
    token_ledger.reset_series()
    yield
    token_ledger.reset_series()


def _sg(n: int, role: str, outcome: str) -> dict:
    return {"sub_game": n, "role": role, "outcome": outcome, "audit_ok": True}


def test_rows_show_per_gamelet_ledger_values() -> None:
    token_ledger.record(30, 12)  # gamelet 1: 42
    token_ledger.reset_gamelet()
    token_ledger.record(5, 5)  # gamelet 2: 10
    token_ledger.reset_gamelet()
    sub_games = [_sg(1, "thief", "survival"), _sg(2, "police", "capture")]
    rows, final = score_series(sub_games, "peer", "peer-vs-vibecode")
    assert rows[0]["tokens"] == {"vibecode": 42, "peer": 0}
    assert rows[1]["tokens"] == {"vibecode": 10, "peer": 0}
    assert final["tokens_total_series"] == {"vibecode": 52, "peer": 0}


def test_opponent_tokens_always_zero_even_with_our_spend() -> None:
    token_ledger.record(100, 100)
    token_ledger.reset_gamelet()
    rows, final = score_series([_sg(1, "thief", "survival")], "peer", "id")
    assert rows[0]["tokens"]["peer"] == 0
    assert final["tokens_total_series"]["peer"] == 0


def test_template_mode_emits_exact_zeros() -> None:
    """LLM disabled (nothing recorded) => artifacts byte-identical to the old zeros."""
    sub_games = [
        _sg(1, "thief", "survival"),
        _sg(2, "police", "capture"),
        _sg(3, "thief", "capture"),
    ]
    rows, final = score_series(sub_games, "peer", "id")
    for row in rows:
        assert row["tokens"] == {"vibecode": 0, "peer": 0}
    assert final["tokens_total_series"] == {"vibecode": 0, "peer": 0}


def test_rows_beyond_closed_history_fall_back_to_zero() -> None:
    """More sub-games than closed gamelet buckets never crashes; extras read 0."""
    token_ledger.record(3, 4)
    token_ledger.reset_gamelet()
    sub_games = [_sg(1, "thief", "survival"), _sg(2, "police", "capture")]
    rows, _final = score_series(sub_games, "peer", "id")
    assert rows[0]["tokens"]["vibecode"] == 7
    assert rows[1]["tokens"]["vibecode"] == 0
