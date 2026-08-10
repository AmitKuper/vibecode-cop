"""Series tie pays +2 to EACH team at the series level (``series_add``).

The book puts the App-F tie score on the accumulated series total; the reference sums
per sub-game; course staff ruled it a documented-choice contradiction. The kit and every
checked league team (imreeyal, anrbj666, best2934) play series-level ADD — a 25-25 series
reports 27/27. The rule itself is declared in the written pairing agreement, never as an
extra result field (the grader's template is the authority).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from ref3_artifacts import score_series  # noqa: E402


def _sg(n: int, role: str, outcome: str) -> dict:
    return {"sub_game": n, "role": role, "outcome": outcome, "audit_ok": True}


def test_level_series_adds_two_to_each_total() -> None:
    # Three captures as cop (20) + three captures as thief (5) = 75 vs 75? No — build a
    # genuinely level 6-game series: each side captures in all its cop games.
    sub_games = [
        _sg(1, "thief", "capture"),
        _sg(2, "police", "capture"),
        _sg(3, "thief", "capture"),
        _sg(4, "police", "capture"),
        _sg(5, "thief", "capture"),
        _sg(6, "police", "capture"),
    ]
    rows, final = score_series(sub_games, "peer", "peer-vs-vibecode")
    assert final["series_tie"] is True
    # Per side: 3 cop captures (3x20) + 3 thief captures conceded (3x5) = 75; +2 tie award.
    assert final["total_score"] == {"vibecode": 77, "peer": 77}
    assert final["winner_group"] is None
    # No extra keys beyond the course template.
    assert "tie_rule" not in final and "tie_score_each" not in final


def test_decided_series_gets_no_award() -> None:
    sub_games = [
        _sg(1, "thief", "survival"),
        _sg(2, "police", "capture"),
        _sg(3, "thief", "survival"),
        _sg(4, "police", "capture"),
        _sg(5, "thief", "survival"),
        _sg(6, "police", "capture"),
    ]
    rows, final = score_series(sub_games, "peer", "peer-vs-vibecode")
    assert final["series_tie"] is False
    # We: thief survival 3x10 + cop capture 3x20 = 90; them: cop 3x5 + thief 3x5 = 30.
    assert final["total_score"] == {"vibecode": 90, "peer": 30}
    assert final["winner_group"] == "vibecode"
