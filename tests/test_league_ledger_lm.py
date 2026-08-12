"""Tests for the league ledger: constraints, persistence, and chain integrity."""

import pytest

from league_manager.league_ledger import MAX_COUNTED_MATCHES, LeagueLedgerError
from tests.helpers_league_ledger_lm import _entry, _ledger

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
