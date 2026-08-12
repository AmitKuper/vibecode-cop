"""Tests for llm/config.py and llm/token_counter.py.

Split from test_uncovered_modules_coverage.py; no LLM, no network.
"""


class TestLLMConfig:
    def test_provider_enum(self):
        from cop_worker.llm.config import LLMProvider

        assert LLMProvider.OLLAMA.value == "ollama"
        assert LLMProvider.ANTHROPIC.value == "anthropic"
        assert LLMProvider.OPENAI.value == "openai"
        assert LLMProvider.AZURE.value == "azure"

    def test_from_dict_ollama(self):
        from cop_worker.llm.config import LLMConfigBuilder, LLMProvider

        cfg = LLMConfigBuilder.from_dict({"provider": "ollama", "model": "llama3.1:8b"})
        assert cfg.provider == LLMProvider.OLLAMA
        assert cfg.model == "llama3.1:8b"

    def test_from_dict_unknown_provider(self):
        from cop_worker.llm.config import LLMConfigBuilder, LLMProvider

        cfg = LLMConfigBuilder.from_dict({"provider": "unknown_xyz"})
        assert cfg.provider == LLMProvider.OLLAMA  # fallback

    def test_to_dict(self):
        from cop_worker.llm.config import LLMConfigBuilder

        cfg = LLMConfigBuilder.from_dict({"provider": "openai", "model": "gpt-4"})
        d = cfg.to_dict()
        assert d["provider"] == "openai"
        assert d["model"] == "gpt-4"

    def test_builder_ollama(self):
        from cop_worker.llm.config import LLMConfigBuilder, LLMProvider

        cfg = LLMConfigBuilder.ollama(model="gemma3:4b")
        assert cfg.provider == LLMProvider.OLLAMA
        assert cfg.model == "gemma3:4b"

    def test_builder_openai(self):
        from cop_worker.llm.config import LLMConfigBuilder, LLMProvider

        cfg = LLMConfigBuilder.openai(model="gpt-4", api_key="sk-test")
        assert cfg.provider == LLMProvider.OPENAI
        assert cfg.api_key == "sk-test"

    def test_builder_anthropic(self):
        from cop_worker.llm.config import LLMConfigBuilder, LLMProvider

        cfg = LLMConfigBuilder.anthropic(model="claude-3-haiku", api_key="ant-key")
        assert cfg.provider == LLMProvider.ANTHROPIC

    def test_builder_azure(self):
        from cop_worker.llm.config import LLMConfigBuilder, LLMProvider

        cfg = LLMConfigBuilder.azure(
            model="gpt-4",
            api_key="key",
            base_url="https://x.openai.azure.com",
        )
        assert cfg.provider == LLMProvider.AZURE


class TestTokenCounter:
    def test_initial_state(self):
        from cop_worker.llm.token_counter import TokenCounter

        c = TokenCounter()
        s = c.summary()
        assert s["prompt_tokens"] == 0
        assert s["completion_tokens"] == 0
        assert s["total_tokens"] == 0
        assert s["llm_calls"] == 0

    def test_record_single(self):
        from cop_worker.llm.token_counter import TokenCounter

        c = TokenCounter()
        c.record(prompt_tokens=100, completion_tokens=50)
        assert c.total == 150
        s = c.summary()
        assert s["llm_calls"] == 1

    def test_record_multiple(self):
        from cop_worker.llm.token_counter import TokenCounter

        c = TokenCounter()
        c.record(10, 5)
        c.record(20, 10)
        assert c.total == 45

    def test_reset(self):
        from cop_worker.llm.token_counter import TokenCounter

        c = TokenCounter()
        c.record(100, 50)
        c.reset()
        assert c.total == 0
        assert c.summary()["llm_calls"] == 0

    def test_record_from_crew_output_none(self):
        from cop_worker.llm.token_counter import TokenCounter

        c = TokenCounter()
        c.record_from_crew_output(object())  # no token_usage attr — should not raise
        assert c.total == 0

    def test_record_from_crew_output_dict(self):
        from cop_worker.llm.token_counter import TokenCounter

        class FakeResult:
            token_usage = {"prompt_tokens": 30, "completion_tokens": 15}

        c = TokenCounter()
        c.record_from_crew_output(FakeResult())
        assert c.total == 45

    def test_thread_safety(self):
        import threading

        from cop_worker.llm.token_counter import TokenCounter

        c = TokenCounter()
        threads = [threading.Thread(target=c.record, args=(10, 5)) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert c.total == 150
