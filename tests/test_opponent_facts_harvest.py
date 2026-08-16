"""Read the opponent's self-declared facts from wherever they actually put them.

Regression for the nis-yar1 friendly (2026-08-16): they sealed `counted_games: 1`
and their `github_commit` in the Step-0 RECORD and put neither in the negotiate
identity. We read only the identity, so our report said their prior count was 0
and their commit "unknown" while their own report said 1 and named the sha - a
disagreement between two counted files is exactly what a grader flags.

The shapes below are taken from that real exchange.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from league_artifacts import opponent_facts  # noqa: E402

NIS_YAR1_SEALED = {
    "type": "step_zero",
    "step": 0,
    "github_commit": "ea475c916acf48248c1a200c9e8450363206b7e5",
    "counted_games": 1,
}
NIS_YAR1_RECORDS = [{"payload": NIS_YAR1_SEALED, "nonce": "n", "commit": "c"}]


def test_counted_count_read_from_the_sealed_record():
    assert opponent_facts.counted_played({}, NIS_YAR1_SEALED) == 1
    assert (
        opponent_facts.counted_played({}, opponent_facts.step_zero_payload(NIS_YAR1_RECORDS)) == 1
    )


def test_commit_read_from_the_sealed_record():
    got = opponent_facts.github_commit({}, opponent_facts.step_zero_payload(NIS_YAR1_RECORDS))
    assert got == "ea475c916acf48248c1a200c9e8450363206b7e5"


def test_all_three_spellings_are_accepted():
    for key in ("counted_games_played", "counted_matches_played", "counted_games"):
        assert opponent_facts.counted_played({key: 4}, {}) == 4


def test_unstated_is_none_not_zero():
    """'They did not say' must not be filed as the claim 'they played zero'."""
    assert opponent_facts.counted_played({}, {}) is None
    assert opponent_facts.counted_played({"group_id": "x"}, {"type": "step_zero"}) is None


def test_zero_is_preserved_when_actually_declared():
    assert opponent_facts.counted_played({"counted_games_played": 0}, {}) == 0


def test_sealed_wins_over_asserted():
    """A signed record outranks an unsigned assertion when the two disagree."""
    identity = {"counted_games_played": 9, "github_commit": "a" * 40}
    assert opponent_facts.counted_played(identity, NIS_YAR1_SEALED) == 1
    assert (
        opponent_facts.github_commit(identity, NIS_YAR1_SEALED) == NIS_YAR1_SEALED["github_commit"]
    )


def test_system_spec_spelling_is_also_a_step_zero():
    """najamjad's spelling of the same record (the mirror-image bug)."""
    records = [{"payload": {"type": "system_spec", "github_commit": "b" * 40}}]
    assert opponent_facts.github_commit({}, opponent_facts.step_zero_payload(records)) == "b" * 40


def test_missing_commit_falls_back_to_unknown():
    assert opponent_facts.github_commit(None, None) == "unknown"


def test_booleans_are_not_counts():
    assert opponent_facts.counted_played({"counted_games": True}, {}) is None


def test_numeric_strings_are_accepted():
    assert opponent_facts.counted_played({"counted_games_played": "3"}, {}) == 3


def test_hardware_spec_from_either_place():
    assert opponent_facts.hardware_spec({"hardware_spec": {"cpu_cores": 8}}, {}) == {"cpu_cores": 8}
    assert opponent_facts.hardware_spec({}, {"spec": {"cpu_cores": 4}}) == {"cpu_cores": 4}
    assert opponent_facts.hardware_spec({}, {}) == {}
