"""Tests for language/hints.py and language/llm_hint.py (non-LLM paths).

Split from test_uncovered_modules_coverage.py; no LLM, no network.
"""


class TestHints:
    def test_generate_hint_north(self):
        from cop_worker.language.hints import generate_hint

        hint = generate_hint("NORTH")
        assert isinstance(hint, str) and len(hint) > 0

    def test_generate_hint_all_directions(self):
        from cop_worker.language.hints import generate_hint

        for move in ["NORTH", "SOUTH", "EAST", "WEST", "STAY"]:
            h = generate_hint(move)
            assert isinstance(h, str)

    def test_generate_hint_lowercase(self):
        from cop_worker.language.hints import generate_hint

        h = generate_hint("north")
        assert isinstance(h, str)

    def test_generate_hint_unknown(self):
        from cop_worker.language.hints import generate_hint

        h = generate_hint("TELEPORT")
        assert "teleport" in h.lower()

    def test_generate_hint_with_rng(self):
        import random

        from cop_worker.language.hints import generate_hint

        rng = random.Random(42)
        h = generate_hint("NORTH", rng=rng)
        assert isinstance(h, str)


class TestLLMHint:
    def test_build_user_prompt_truth(self):
        from cop_worker.language.llm_hint import _build_user_prompt

        p = _build_user_prompt("N", "truth")
        assert "north" in p.lower()
        assert "truth" in p.lower() or "Tell" in p

    def test_build_user_prompt_lie(self):
        from cop_worker.language.llm_hint import _build_user_prompt

        p = _build_user_prompt("N", "lie")
        assert isinstance(p, str)

    def test_llm_hint_generator_no_provider(self):
        from cop_worker.language.llm_hint import LLMHintGenerator

        gen = LLMHintGenerator(provider="none_exist")
        result = gen.generate("N", "truth")
        assert result is None  # no provider = None

    def test_from_llm_config(self):
        from cop_worker.language.llm_hint import LLMHintGenerator

        gen = LLMHintGenerator.from_llm_config(
            {
                "provider": "ollama",
                "model": "test",
                "base_url": "http://localhost:99999",
                "hint_timeout": 0.001,
            }
        )
        result = gen.generate("S", "truth")
        assert result is None  # connection will fail silently
