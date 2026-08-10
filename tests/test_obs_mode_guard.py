"""A stray obs-mode env flag must refuse to load, never silently change the observation.

``COPTHIEF_DECODED_SCENT`` and ``COPTHIEF_SCENT_MODEL`` alter what the net reads at
SERVING time. If the live value contradicts what the manifest recorded for the promoted
artifact, the net plays on inputs it never trained on — the 0.9608→0.3185 shape. The
guard fires at load, loudly, before a single move is played.
"""

from __future__ import annotations

import pytest

from cop_worker.rl.counted_policy import CountedPolicyLoadError, _guard_serving_obs_mode


class _Entry:
    def __init__(self, obs_mode):
        self.obs_mode = obs_mode


def test_defaults_pass_for_pre_switch_manifests(monkeypatch) -> None:
    monkeypatch.delenv("COPTHIEF_DECODED_SCENT", raising=False)
    monkeypatch.delenv("COPTHIEF_SCENT_MODEL", raising=False)
    _guard_serving_obs_mode(_Entry(None), "cop")
    _guard_serving_obs_mode(_Entry({}), "cop")


def test_stray_decoded_scent_refuses(monkeypatch) -> None:
    monkeypatch.setenv("COPTHIEF_DECODED_SCENT", "1")
    monkeypatch.setenv("COPTHIEF_WIRE_SCENT", "1")
    monkeypatch.delenv("COPTHIEF_SCENT_MODEL", raising=False)
    with pytest.raises(CountedPolicyLoadError, match="DECODED_SCENT"):
        _guard_serving_obs_mode(_Entry({"decoded_scent": False}), "thief")


def test_decoder_trained_artifact_requires_the_flag(monkeypatch) -> None:
    monkeypatch.delenv("COPTHIEF_DECODED_SCENT", raising=False)
    monkeypatch.delenv("COPTHIEF_SCENT_MODEL", raising=False)
    with pytest.raises(CountedPolicyLoadError, match="DECODED_SCENT"):
        _guard_serving_obs_mode(_Entry({"decoded_scent": True}), "cop")


def test_scent_model_mismatch_refuses_both_directions(monkeypatch) -> None:
    monkeypatch.delenv("COPTHIEF_DECODED_SCENT", raising=False)
    monkeypatch.setenv("COPTHIEF_SCENT_MODEL", "chebyshev")
    with pytest.raises(CountedPolicyLoadError, match="scent_model"):
        _guard_serving_obs_mode(_Entry({"scent_model": "multiplicative_book_v1"}), "cop")
    monkeypatch.delenv("COPTHIEF_SCENT_MODEL", raising=False)
    with pytest.raises(CountedPolicyLoadError, match="scent_model"):
        _guard_serving_obs_mode(_Entry({"scent_model": "subtractive_chebyshev_v1"}), "thief")


def test_matching_chebyshev_configuration_passes(monkeypatch) -> None:
    monkeypatch.delenv("COPTHIEF_DECODED_SCENT", raising=False)
    monkeypatch.setenv("COPTHIEF_SCENT_MODEL", "subtractive_chebyshev_v1")
    _guard_serving_obs_mode(
        _Entry({"scent_model": "subtractive_chebyshev_v1", "decoded_scent": False}), "cop"
    )
