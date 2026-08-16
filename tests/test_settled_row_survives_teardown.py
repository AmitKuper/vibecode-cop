"""A window whose audit verified must never be filed as a failure.

Reproduces the nis-yar1 sub-game 5 loss, which happened twice (2026-08-12 and
2026-08-16): the audit passed, and in the SAME millisecond their cloudflared
tunnel returned 502. The row existed; the exception threw it away; the worker
reported a bare failure; the settlement guard then withheld the whole series
report because only 5/6 windows had settled. A won sub-game became a lost series.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ref3_match import settled_row  # noqa: E402


class _Session:
    """Stands in for the session shared by the worker and the settle step."""


def _row(sub_game: int = 5, outcome: str = "survival") -> dict:
    return {"sub_game": sub_game, "role": "thief", "audit_ok": True, "outcome": outcome}


def test_recover_returns_the_row_after_settlement():
    s = _Session()
    settled_row.remember(s, _row())
    got = settled_row.recover(s, 5)
    assert got is not None and got["audit_ok"] is True and got["outcome"] == "survival"


def test_nothing_to_recover_before_settlement():
    assert settled_row.recover(_Session(), 5) is None


def test_a_row_only_answers_for_its_own_window():
    s = _Session()
    settled_row.remember(s, _row(sub_game=5))
    assert settled_row.recover(s, 6) is None, "window 5's row must not settle window 6"


def test_forget_clears_between_windows():
    s = _Session()
    settled_row.remember(s, _row(sub_game=5))
    settled_row.forget(s)
    assert settled_row.recover(s, 5) is None


def test_the_real_sequence_audit_then_502():
    """End-to-end shape of the failure: settle, then the peer's endpoint dies."""
    session = _Session()
    settled_row.forget(session)  # window start

    def settle() -> dict:
        row = _row()
        settled_row.remember(session, row)  # the instant the audit verified
        return row

    def worker_window() -> dict:
        try:
            settle()
            raise RuntimeError("HTTPStatusError: Server error '502 Bad Gateway'")
        except Exception as exc:
            recovered = settled_row.recover(session, 5)
            if recovered is not None:
                recovered["post_settlement_error"] = str(exc)
                return {"type": "result", "row": recovered}
            return {"type": "fail", "error": str(exc)}

    frame = worker_window()
    assert frame["type"] == "result", "a verified window was filed as a failure again"
    assert frame["row"]["audit_ok"] is True
    assert "502" in frame["row"]["post_settlement_error"], "the noise is recorded, not hidden"


def test_a_genuine_pre_settlement_failure_still_fails():
    """The guard must not turn real failures into phantom settlements."""
    session = _Session()
    settled_row.forget(session)
    try:
        raise RuntimeError("peer never greeted")
    except Exception as exc:
        assert settled_row.recover(session, 5) is None
        frame = {"type": "fail", "error": str(exc)}
    assert frame["type"] == "fail"
