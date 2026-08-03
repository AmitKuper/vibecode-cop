"""Tests for the league ledger: constraints, persistence, and chain integrity."""

import pytest

from agent.step0.league_ledger import (
    MAX_COUNTED_MATCHES,
    LeagueLedger,
    LeagueLedgerError,
    LedgerEntry,
)


def _entry(opponent_id: str, counted: bool, match_id: str = "") -> LedgerEntry:
    return LedgerEntry(
        opponent_id=opponent_id,
        match_id=match_id or f"match-{opponent_id}",
        counted=counted,
        declaration_hash="decl-hash",
        result_hash="result-hash",
        timestamp_utc="2026-01-01T00:00:00+00:00",
    )


def _ledger(tmp_path) -> LeagueLedger:
    return LeagueLedger(str(tmp_path / "ledger.json"))


# ---------------------------------------------------------------------------
# Empty ledger
# ---------------------------------------------------------------------------


def test_empty_ledger_no_counted_opponents(tmp_path):
    ll = _ledger(tmp_path)
    assert ll.counted_opponents() == set()


def test_empty_ledger_count_zero(tmp_path):
    ll = _ledger(tmp_path)
    assert ll.counted_match_count() == 0


def test_empty_ledger_root_is_sentinel(tmp_path):
    ll = _ledger(tmp_path)
    root = ll.ledger_root()
    assert len(root) == 64  # SHA-256 hex
    int(root, 16)


def test_empty_has_minimum_groups_false(tmp_path):
    ll = _ledger(tmp_path)
    assert ll.has_minimum_different_groups() is False


# ---------------------------------------------------------------------------
# Warm-up (non-counted) entry
# ---------------------------------------------------------------------------


def test_append_warmup_succeeds(tmp_path):
    ll = _ledger(tmp_path)
    ll.append(_entry("opponent-A", counted=False))
    assert ll.counted_match_count() == 0
    assert "opponent-A" not in ll.counted_opponents()


# ---------------------------------------------------------------------------
# Counted entries
# ---------------------------------------------------------------------------


def test_append_counted_entry_succeeds(tmp_path):
    ll = _ledger(tmp_path)
    ll.append(_entry("opponent-B", counted=True))
    assert ll.counted_match_count() == 1
    assert "opponent-B" in ll.counted_opponents()


def test_append_duplicate_counted_opponent_raises(tmp_path):
    ll = _ledger(tmp_path)
    ll.append(_entry("opponent-C", counted=True, match_id="match-1"))
    with pytest.raises(LeagueLedgerError, match="opponent-C"):
        ll.append(_entry("opponent-C", counted=True, match_id="match-2"))


def test_counted_match_count_increments(tmp_path):
    ll = _ledger(tmp_path)
    ll.append(_entry("opp-1", counted=True))
    ll.append(_entry("opp-2", counted=True))
    assert ll.counted_match_count() == 2


# ---------------------------------------------------------------------------
# MAX_COUNTED_MATCHES enforcement
# ---------------------------------------------------------------------------


def test_append_at_max_counted_matches_raises(tmp_path):
    ll = _ledger(tmp_path)
    for i in range(MAX_COUNTED_MATCHES):
        ll.append(_entry(f"opp-{i}", counted=True))
    assert ll.counted_match_count() == MAX_COUNTED_MATCHES
    with pytest.raises(LeagueLedgerError, match="Max counted matches"):
        ll.append(_entry("opp-extra", counted=True))


def test_warmup_after_max_counted_still_ok(tmp_path):
    ll = _ledger(tmp_path)
    for i in range(MAX_COUNTED_MATCHES):
        ll.append(_entry(f"opp-{i}", counted=True))
    # warm-up (non-counted) must still succeed
    ll.append(_entry("opp-warmup", counted=False))
    assert ll.counted_match_count() == MAX_COUNTED_MATCHES


# ---------------------------------------------------------------------------
# Persistence and reload
# ---------------------------------------------------------------------------


def test_ledger_persists_and_reloads(tmp_path):
    path = str(tmp_path / "ledger.json")
    ll1 = LeagueLedger(path)
    ll1.append(_entry("opp-persist-A", counted=True))
    ll1.append(_entry("opp-persist-B", counted=False))

    ll2 = LeagueLedger(path)
    assert ll2.counted_match_count() == 1
    assert "opp-persist-A" in ll2.counted_opponents()


def test_ledger_chain_previous_hash(tmp_path):
    ll = _ledger(tmp_path)
    initial_root = ll.ledger_root()
    e1 = _entry("opp-X", counted=True)
    ll.append(e1)
    assert e1.previous_entry_hash == initial_root


def test_ledger_reload_rejects_duplicate(tmp_path):
    path = str(tmp_path / "ledger.json")
    ll1 = LeagueLedger(path)
    ll1.append(_entry("opp-dup", counted=True, match_id="m1"))

    ll2 = LeagueLedger(path)
    with pytest.raises(LeagueLedgerError):
        ll2.append(_entry("opp-dup", counted=True, match_id="m2"))


# ---------------------------------------------------------------------------
# has_minimum_different_groups
# ---------------------------------------------------------------------------


def test_has_minimum_groups_false_with_one(tmp_path):
    ll = _ledger(tmp_path)
    ll.append(_entry("opp-solo", counted=True))
    assert ll.has_minimum_different_groups() is False


def test_has_minimum_groups_true_with_two(tmp_path):
    ll = _ledger(tmp_path)
    ll.append(_entry("opp-1", counted=True))
    ll.append(_entry("opp-2", counted=True))
    assert ll.has_minimum_different_groups() is True


def test_has_minimum_groups_warmup_does_not_count(tmp_path):
    ll = _ledger(tmp_path)
    ll.append(_entry("opp-wu-1", counted=False))
    ll.append(_entry("opp-wu-2", counted=False))
    assert ll.has_minimum_different_groups() is False
