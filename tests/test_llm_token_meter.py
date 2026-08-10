"""G9: real LLM token metering — Ollama counts accumulate and reach the result."""

from __future__ import annotations

import cop_worker.language.llm_hint as llm_hint


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_ollama_counts_accumulate(monkeypatch) -> None:
    llm_hint.reset_token_totals()

    def fake_post(url, json=None, timeout=None):
        return _Resp(
            {
                "message": {"content": "the shadows move north tonight"},
                "prompt_eval_count": 41,
                "eval_count": 9,
            }
        )

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    assert llm_hint._call_ollama("http://x", "m", "N", "mislead", 1.0) is not None
    assert llm_hint._call_ollama("http://x", "m", "S", "mislead", 1.0) is not None
    totals = llm_hint.token_totals()
    assert totals == {"prompt": 82, "completion": 18, "total": 100}


def test_failed_call_records_nothing(monkeypatch) -> None:
    llm_hint.reset_token_totals()

    def fake_post(url, json=None, timeout=None):
        raise OSError("down")

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    assert llm_hint._call_ollama("http://x", "m", "N", "mislead", 1.0) is None
    assert llm_hint.token_totals() == {"prompt": 0, "completion": 0, "total": 0}


def test_result_carries_real_totals(monkeypatch) -> None:
    llm_hint.reset_token_totals()
    llm_hint._record_tokens(7, 3)
    from cop_worker.gamelet import Gamelet

    # Call through a minimal stand-in carrying the attributes _build_result reads.
    class _Stub:
        game_uid = "uid"
        sub_game_number = 1
        role = "police"
        _step = 5
        _audit_records = []

    stub = _Stub()
    built = Gamelet._build_result(stub, True)
    assert built["llm_tokens"] == {"prompt": 7, "completion": 3, "total": 10}
