"""Pins for the najamjad-friendly forensic fixes (2026-08-13):
(1) concession-shaped trails are not disputed; (2) an incomplete series can never
assert confirmed mutual consensus; (3) opponent token totals are harvested from
their step-0 declarations instead of hardcoded zero.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from league_artifacts.result import build_result  # noqa: E402
from league_artifacts.scoring import score_series  # noqa: E402
from ref3_match.subgame_settle import _refine_disputed_trail  # noqa: E402


def _rec(step, pos):
    return {"payload": {"step": step, "position": pos}}


def test_trail_ending_on_caught_cell_not_disputed():
    recs = [_rec(10, [4, 5]), _rec(11, [5, 5])]
    assert _refine_disputed_trail(recs, [5, 5], 2) is None


def test_concession_shape_one_post_answer_record_not_disputed():
    # najamjad 2026-08-13 (all three capture windows): caught cell at trail[-2],
    # the step-12 concession record carries one more move.
    recs = [_rec(10, [4, 5]), _rec(11, [5, 5]), _rec(12, [4, 5])]
    assert _refine_disputed_trail(recs, [5, 5], 4) is None


def test_genuinely_wrong_trail_still_disputed():
    recs = [_rec(10, [1, 1]), _rec(11, [2, 1]), _rec(12, [3, 1])]
    disputed = _refine_disputed_trail(recs, [5, 5], 6)
    assert disputed and disputed["kind"] == "trail_end_mismatch"


def _row(n, verified=True):
    return {
        "sub_game_number": n,
        "roles": {"vibecode": "thief", "x": "police"},
        "result": "survival",
        "winner_group": "vibecode",
        "score": {"vibecode": 10, "x": 5},
        "audit": {"log_verified": verified, "tampered": False},
    }


def _final():
    return {
        "series_tie": False,
        "sub_games_won": {"vibecode": 4, "x": 0},
        "ties": 0,
        "total_score": {"vibecode": 70, "x": 20},
        "winner_group": "vibecode",
    }


def test_incomplete_series_never_confirmed():
    result = build_result("x-vs-vibecode", "uid", "x", [_row(n) for n in (1, 2, 4, 6)], _final())
    assert result["mutual_agreement"]["confirmed"] is False
    assert result["series_complete"] is False and result["sub_games_expected"] == 6


def test_complete_series_confirmed_and_unannotated():
    result = build_result("x-vs-vibecode", "uid", "x", [_row(n) for n in range(1, 7)], _final())
    assert result["mutual_agreement"]["confirmed"] is True
    assert "series_complete" not in result  # byte-compatible with prior filed results


def test_opponent_tokens_harvested_from_step0():
    def sg(n, cum):
        return {
            "sub_game": n,
            "role": "thief" if n % 2 else "police",
            "outcome": "survival" if n % 2 else "capture",
            "audit_ok": True,
            "opp_records": [{"payload": {"type": "system_spec", "tokens_total": cum}}],
        }

    rows, final = score_series([sg(1, 97), sg(2, 4894), sg(3, 6702)], "x", "x-vs-vibecode")
    assert [r["tokens"]["x"] for r in rows] == [97, 4797, 1808]  # cumulative -> per-window deltas
    assert final["tokens_total_series"]["x"] == 6702
    # A peer sending no token field stays at honest zero.
    rows2, final2 = score_series(
        [{"sub_game": 1, "role": "thief", "outcome": "survival", "audit_ok": True}],
        "y",
        "y-vs-vibecode",
    )
    assert rows2[0]["tokens"]["y"] == 0 and final2["tokens_total_series"]["y"] == 0
