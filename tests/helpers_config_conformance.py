"""Shared fixtures for the CanonicalConfig cross-repo conformance test modules."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Minimal valid flat config (all Appendix-F fields, all constraints met)
# ---------------------------------------------------------------------------
_VALID_FLAT = {
    "grid_size": 7,
    "max_barriers": 14,
    "max_turns": 35,
    "survival_threshold": 35,
    "num_gamelets": 6,
    "min_games_to_pass": 2,
    "max_counted_games": 10,
    "diversity_reward": 10,
    "capture_cop": 20,
    "capture_thief": 5,
    "survival_cop": 5,
    "survival_thief": 10,
    "scent_center": 0.9,
    "scent_decay": 0.10,
    "scent_field_size": 5,
}


def _make(**overrides) -> dict:
    d = dict(_VALID_FLAT)
    d.update(overrides)
    return d


def _drop(field: str) -> dict:
    d = dict(_VALID_FLAT)
    del d[field]
    return d
