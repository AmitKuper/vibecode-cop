"""Behavioral tests for cop_worker.language.llm_hint (no network: httpx mocked)."""

from __future__ import annotations

import httpx
import pytest

from cop_worker.language.llm_hint import (
    LLMHintGenerator,
    _build_user_prompt,
    _call_crewai_llm,
    _call_ollama,
)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"message": {"content": self._content}}


def _patch_post(monkeypatch, content: str | None, error: bool = False) -> list:
    calls: list = []

    def fake_post(url, json=None, timeout=None):
        calls.append({"url": url, "payload": json, "timeout": timeout})
        if error:
            raise httpx.ConnectError("refused")
        return _FakeResponse(content or "")

    monkeypatch.setattr(httpx, "post", fake_post)
    return calls


@pytest.mark.parametrize("intent", ["truth", "lie", "ambiguous", "bluff", "unknown"])
def test_build_user_prompt_intents(intent):
    prompt = _build_user_prompt("N", intent)
    assert "north" in prompt and "One sentence only." in prompt


def test_build_user_prompt_unknown_move():
    prompt = _build_user_prompt("JUMP", "truth")
    assert "jump" in prompt


def test_call_ollama_success_and_payload(monkeypatch):
    calls = _patch_post(monkeypatch, "Heading north.")
    text = _call_ollama("http://localhost:11434/", "m", "N", "truth", 1.0, keep_alive="5m")
    assert text == "Heading north."
    assert calls[0]["url"] == "http://localhost:11434/api/chat"
    assert calls[0]["payload"]["keep_alive"] == "5m"


def test_call_ollama_truncates_long_reply(monkeypatch):
    _patch_post(monkeypatch, "w " * 30)
    text = _call_ollama("http://x", "m", "S", "lie", 1.0)
    assert text is not None and len(text.split()) == 15


def test_call_ollama_empty_and_error(monkeypatch):
    _patch_post(monkeypatch, "")
    assert _call_ollama("http://x", "m", "E", "truth", 1.0) is None
    _patch_post(monkeypatch, None, error=True)
    assert _call_ollama("http://x", "m", "E", "truth", 1.0) is None


class _FakeLLM:
    def __init__(self, reply):
        self.reply = reply

    def call(self, messages):
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def test_call_crewai_llm_paths():
    assert _call_crewai_llm(_FakeLLM("Going west."), "W", "truth", 1.0) == "Going west."
    long = _call_crewai_llm(_FakeLLM("x " * 20), "W", "truth", 1.0)
    assert long is not None and len(long.split()) == 15
    assert _call_crewai_llm(_FakeLLM(["not", "a", "str"]), "W", "truth", 1.0) is None
    assert _call_crewai_llm(_FakeLLM(""), "W", "truth", 1.0) is None
    assert _call_crewai_llm(_FakeLLM(RuntimeError("boom")), "W", "truth", 1.0) is None


def test_generate_dispatch(monkeypatch):
    _patch_post(monkeypatch, "North it is.")
    gen = LLMHintGenerator(provider="ollama")
    assert gen.generate("N", "truth") == "North it is."
    gen2 = LLMHintGenerator(provider="openai", llm=_FakeLLM("Sneaky east."))
    assert gen2.generate("E", "bluff") == "Sneaky east."
    gen3 = LLMHintGenerator(provider="openai", llm=None)
    assert gen3.generate("E", "truth") is None


def test_warmup_paths(monkeypatch):
    _patch_post(monkeypatch, "warm")
    assert LLMHintGenerator(provider="ollama").warmup(timeout=1.0) is True
    _patch_post(monkeypatch, None, error=True)
    assert LLMHintGenerator(provider="ollama").warmup(timeout=1.0) is False
    assert LLMHintGenerator(provider="openai", llm=_FakeLLM("x")).warmup() is True
    assert LLMHintGenerator(provider="openai", llm=None).warmup() is False


def test_from_llm_config_defaults_and_overrides():
    gen = LLMHintGenerator.from_llm_config({})
    assert gen.provider == "ollama" and gen.timeout == 3.0
    cfg = {
        "provider": "openai",
        "model": "gpt-x",
        "base_url": "http://b",
        "hint_timeout": "1.5",
        "keep_alive": "1m",
    }
    gen2 = LLMHintGenerator.from_llm_config(cfg, llm=_FakeLLM("y"))
    assert gen2.provider == "openai" and gen2.timeout == 1.5 and gen2.keep_alive == "1m"
