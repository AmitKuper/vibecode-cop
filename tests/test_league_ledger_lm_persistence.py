"""Tests for the league ledger: persistence, reload, and group-minimum checks."""

import pytest

from league_manager.league_ledger import LeagueLedger, LeagueLedgerError
from tests.helpers_league_ledger_lm import _entry, _ledger

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
