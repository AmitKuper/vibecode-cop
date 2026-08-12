"""Targeted tests for modules the 2026-08-10 additions left under the CI coverage gate.

This part pins the scent fingerprint's model classification (log-only, but it fed a
live MISMATCH banner) and the obs-mode env contract.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# cop_worker.protocol.scent_fingerprint
# ---------------------------------------------------------------------------
from cop_worker.protocol.scent_fingerprint import agrees_with_us, fingerprint


class TestScentFingerprint:
    def test_book_fresh_field_classifies_book(self) -> None:
        grid = {"3,3": 0.9, "3,4": 0.62, "3,5": 0.42, "2,2": 0.14, "1,1": 0.04}
        result = fingerprint(grid)
        assert result["model"] == "multiplicative_book_v1"
        assert result["book_only_hits"] >= 3
        assert result["sha256"].startswith("934c220d")

    def test_chebyshev_fresh_rings_classify_chebyshev(self) -> None:
        result = fingerprint({"3,3": 0.9, "3,4": 0.6, "3,5": 0.3})
        assert result["model"] == "subtractive_chebyshev_v1"
        assert result["sha256"].startswith("81ebee59")

    def test_decayed_chebyshev_lattice_classifies_chebyshev(self) -> None:
        # The kit's own wire frame: after-one-decay {0.8, 0.5, 0.2} — the exact live
        # frame that misclassified as book before the 0.1-lattice rule.
        result = fingerprint({"3,3": 0.8, "3,4": 0.5, "3,5": 0.2, "2,3": 0.5})
        assert result["model"] == "subtractive_chebyshev_v1"

    def test_two_lattice_cells_are_not_decisive(self) -> None:
        # 0.2/0.9 exist in both models; fewer than three cells never decide.
        assert fingerprint({"0,0": 0.2, "1,1": 0.9})["model"] == "inconclusive"

    def test_empty_and_mixed_evidence(self) -> None:
        assert fingerprint({})["model"] == "empty"
        assert fingerprint(None)["model"] == "empty"
        mixed = fingerprint({"1,1": 0.62, "2,2": 0.6, "3,3": 0.3})
        assert mixed["model"] == "inconclusive"

    def test_agrees_with_us_tri_state(self) -> None:
        assert agrees_with_us({"3,3": 0.9, "3,4": 0.62, "2,2": 0.42}) is True
        assert agrees_with_us({"3,3": 0.9, "3,4": 0.6, "3,5": 0.3}) is False
        assert agrees_with_us({}) is None


# ---------------------------------------------------------------------------
# cop_worker.rl.obs_mode
# ---------------------------------------------------------------------------
from cop_worker.rl import obs_mode


class TestObsMode:
    def test_unknown_scent_model_is_a_configuration_error(self, monkeypatch) -> None:
        monkeypatch.setenv(obs_mode.SCENT_MODEL_ENV, "no_such_model")
        with pytest.raises(ValueError, match="not a registered scent model"):
            obs_mode.scent_model()

    def test_shorthands_resolve_to_registered_names(self, monkeypatch) -> None:
        monkeypatch.setenv(obs_mode.SCENT_MODEL_ENV, "chebyshev")
        assert obs_mode.scent_model() == "subtractive_chebyshev_v1"
        assert obs_mode.chebyshev_scent_enabled() is True
        monkeypatch.setenv(obs_mode.SCENT_MODEL_ENV, "book")
        assert obs_mode.scent_model() == "multiplicative_book_v1"

    def test_describe_and_tag_reflect_all_switches(self, monkeypatch) -> None:
        monkeypatch.setenv(obs_mode.UNIFORM_BELIEF_ENV, "1")
        monkeypatch.setenv(obs_mode.WIRE_SCENT_ENV, "1")
        monkeypatch.setenv(obs_mode.DECODED_SCENT_ENV, "1")
        monkeypatch.setenv(obs_mode.SCENT_MODEL_ENV, "chebyshev")
        described = obs_mode.describe()
        assert described == {
            "uniform_belief": True,
            "wire_scent": True,
            "decoded_scent": True,
            "scent_model": "subtractive_chebyshev_v1",
        }
        tag = obs_mode.observation_mode_tag()
        for part in ("uniformbelief", "wirescent", "decodedscent", "chebyshev"):
            assert part in tag

    def test_legacy_tag_when_everything_off(self, monkeypatch) -> None:
        for env in (
            obs_mode.UNIFORM_BELIEF_ENV,
            obs_mode.WIRE_SCENT_ENV,
            obs_mode.DECODED_SCENT_ENV,
            obs_mode.SCENT_MODEL_ENV,
        ):
            monkeypatch.delenv(env, raising=False)
        assert obs_mode.observation_mode_tag() == "legacy-research-obs"
