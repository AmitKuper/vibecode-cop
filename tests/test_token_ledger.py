"""Token ledger: arithmetic, thread safety, and real LLM usage flowing into it."""

from __future__ import annotations

import threading

import pytest

import cop_worker.language.llm_hint as llm_hint
from cop_worker.language import token_ledger


@pytest.fixture(autouse=True)
def _fresh_ledger():
    token_ledger.reset_series()
    llm_hint.reset_token_totals()
    yield
    token_ledger.reset_series()
    llm_hint.reset_token_totals()


def test_record_accumulates_gamelet_and_series() -> None:
    token_ledger.record(10, 5)
    token_ledger.record(2, 3)
    assert token_ledger.gamelet_total() == 20
    assert token_ledger.series_total() == 20


def test_reset_gamelet_closes_bucket_but_keeps_series() -> None:
    token_ledger.record(10, 5)
    closed = token_ledger.reset_gamelet()
    assert closed == 15
    assert token_ledger.gamelet_total() == 0
    assert token_ledger.series_total() == 15
    token_ledger.record(1, 1)
    token_ledger.reset_gamelet()
    assert token_ledger.gamelet_history() == [15, 2]
    assert token_ledger.series_total() == 17


def test_reset_series_zeroes_everything() -> None:
    token_ledger.record(4, 4)
    token_ledger.reset_gamelet()
    token_ledger.reset_series()
    assert token_ledger.gamelet_total() == 0
    assert token_ledger.series_total() == 0
    assert token_ledger.gamelet_history() == []


def test_record_is_thread_safe() -> None:
    def _hammer():
        for _ in range(500):
            token_ledger.record(1, 1)

    threads = [threading.Thread(target=_hammer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert token_ledger.series_total() == 8 * 500 * 2


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_llm_backend_usage_reaches_ledger(monkeypatch) -> None:
    """A backend response carrying usage counts records REAL tokens into the ledger."""

    def fake_post(url, json=None, timeout=None):
        return _Resp(
            {
                "message": {"content": "the shadows move north"},
                "prompt_eval_count": 41,
                "eval_count": 9,
            }
        )

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    assert llm_hint._call_ollama("http://x", "m", "N", "mislead", 1.0) is not None
    assert token_ledger.gamelet_total() == 50
    assert token_ledger.series_total() == 50


def test_template_path_records_nothing() -> None:
    """Template hint generation never touches the LLM, so the ledger stays 0."""
    from cop_worker.language.hints import generate_hint

    for move in ("NORTH", "SOUTH", "STAY"):
        assert generate_hint(move)
    assert token_ledger.series_total() == 0
    assert token_ledger.gamelet_total() == 0
