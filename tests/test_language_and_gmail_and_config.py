"""Fast unit tests for deception language policy, DoS detector, league config.

Pure/deterministic — no LLM (templates only), no network, no sleeps.
"""

from __future__ import annotations

import random

import pytest

from cop_worker.language.deception_policy import DeceptionIntent, NaturalLanguagePolicy
from league_manager.config.league_config import (
    ConfigValidationError,
    LeagueConfig,
    load_config,
    validate_group_id,
)
from league_manager.gmail.dos_detector import DosDetector

# --- deception policy (templates, no LLM) -----------------------------------


def test_choose_intent_low_token_budget_is_ambiguous():
    pol = NaturalLanguagePolicy(role="cop")
    assert pol.choose_intent(step=1, token_budget=3) == DeceptionIntent.AMBIGUOUS


def test_choose_intent_returns_valid_enum_across_contexts():
    pol = NaturalLanguagePolicy(role="thief", bluff_probability=0.3)
    random.seed(0)
    seen = {
        pol.choose_intent(step=s, belief_entropy=e, physical_action=a)
        for s in range(6)
        for e in (0.0, 2.0, 4.0)
        for a in ("N", "STAY", "PLACE_E")
    }
    assert seen and seen.issubset(set(DeceptionIntent))


def test_generate_truth_and_lie_templates():
    pol = NaturalLanguagePolicy(role="cop")
    random.seed(1)
    truth = pol.generate("N", DeceptionIntent.TRUTH)
    lie = pol.generate("N", DeceptionIntent.LIE)
    assert truth in NaturalLanguagePolicy.TRUTH_TEMPLATES["N"]
    assert lie in NaturalLanguagePolicy.LIE_TEMPLATES["N"]


def test_generate_prefers_llm_when_available():
    class _Stub:
        def generate(self, move, intent):
            return f"llm:{move}:{intent}"

    pol = NaturalLanguagePolicy(role="cop", llm_hint_generator=_Stub())
    assert pol.generate("E", DeceptionIntent.TRUTH) == "llm:E:truth"


def test_generate_falls_back_to_template_on_llm_error():
    class _Boom:
        def generate(self, move, intent):
            raise RuntimeError("no")

    pol = NaturalLanguagePolicy(role="cop", llm_hint_generator=_Boom())
    out = pol.generate("STAY", DeceptionIntent.AMBIGUOUS)
    assert out in NaturalLanguagePolicy.AMBIGUOUS_TEMPLATES


def test_record_and_count_opponent_hints():
    pol = NaturalLanguagePolicy(role="cop")
    pol.record_opponent_hint("Moving north.", trustworthy=True)
    pol.record_opponent_hint("Going 3,4 now")
    assert pol.opponent_hint_count() == 2


def test_hint_is_numeric_location_detection():
    pol = NaturalLanguagePolicy(role="cop")
    assert pol.hint_is_numeric_location("I am at 3,4")
    assert pol.hint_is_numeric_location("row 2 blocked")
    assert not pol.hint_is_numeric_location("Heading north.")


# --- DoS detector (uses monotonic clock; no sleeps needed) ------------------


def test_dos_detector_allows_under_limits():
    d = DosDetector(max_per_minute=10, max_per_game=2)
    allowed, reason = d.check("g1")
    assert allowed and reason == "" and not d.is_locked


def test_dos_detector_locks_on_repeated_game_id():
    d = DosDetector(max_per_minute=100, max_per_game=2)
    d.check("g1")
    d.check("g1")
    allowed, reason = d.check("g1")  # third for same game → over per-game limit
    assert not allowed and "Repeated game_id" in reason and d.is_locked


def test_dos_detector_locks_on_burst():
    d = DosDetector(max_per_minute=3, max_per_game=100)
    for i in range(3):
        d.check(f"g{i}")
    allowed, reason = d.check("g99")
    assert not allowed and "Burst detected" in reason


def test_dos_detector_reset_lock():
    d = DosDetector(max_per_minute=1, max_per_game=100)
    d.check("a")
    d.check("b")  # trips burst lock
    assert d.is_locked
    d.reset_lock()
    assert not d.is_locked


# --- league config ----------------------------------------------------------


def test_validate_group_id_accepts_8_alnum():
    validate_group_id("abcd1234")  # must not raise


@pytest.mark.parametrize("bad", ["short", "toolonggroup", "abcd-123", "abcd 123"])
def test_validate_group_id_rejects_bad(bad):
    with pytest.raises(ConfigValidationError):
        validate_group_id(bad)


def test_league_config_post_init_validates_group_id():
    with pytest.raises(ConfigValidationError):
        LeagueConfig(group_id="bad")
    cfg = LeagueConfig(group_id="abcd1234")
    assert cfg.network.port == 8000 and cfg.match.counted is False


def test_load_config_from_yaml(tmp_path):
    p = tmp_path / "league.yaml"
    p.write_text(
        "group_id: abcd1234\n"
        "network:\n  port: 9000\n  cop_url: http://x:1\n"
        "match:\n  counted: true\n  starting_role: thief\n"
        "output:\n  log_dir: mylogs\n  report_dir: myreports\n"
    )
    cfg = load_config(p)
    assert cfg.group_id == "abcd1234"
    assert cfg.network.port == 9000
    assert cfg.match.counted is True and cfg.match.starting_role == "thief"
    assert cfg.log_dir == "mylogs" and cfg.report_dir == "myreports"
