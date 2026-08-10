"""Single configuration authority with metadata and SHA-256 commitment.

CanonicalConfig is the sole validator for all Appendix-F parameters.
agent/domain/config_validator.py is DEPRECATED — it now delegates here.

Field metadata:
  FIXED      — must match exactly; changing is a binding rule violation
  MINIMUM    — must be >= floor; peers may negotiate higher values
  NEGOTIATED — agreed per-series; no hard floor/ceiling encoded here
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from cop_worker.config.canonical_config_views import CanonicalConfigViewsMixin


class FieldKind(StrEnum):
    FIXED = "FIXED"
    MINIMUM = "MINIMUM"
    NEGOTIATED = "NEGOTIATED"


class ConfigError(ValueError):
    """Raised when canonical config validation fails."""


# ---------------------------------------------------------------------------
# Appendix-F field registry
# (name, kind, fixed_value_or_None, minimum_or_None)
# ---------------------------------------------------------------------------
_FIELD_SPECS: list[tuple[str, FieldKind, Any, Any]] = [
    # Board
    ("grid_size", FieldKind.MINIMUM, None, 7),
    # Movement / barriers
    ("max_barriers", FieldKind.MINIMUM, None, 14),
    ("max_turns", FieldKind.MINIMUM, None, 35),
    ("survival_threshold", FieldKind.MINIMUM, None, 35),
    # League / series
    ("num_gamelets", FieldKind.FIXED, 6, None),
    ("min_games_to_pass", FieldKind.FIXED, 2, None),
    ("max_counted_games", FieldKind.FIXED, 10, None),
    ("diversity_reward", FieldKind.FIXED, 10, None),
    # Scoring (Appendix-F mandatory table)
    ("capture_cop", FieldKind.FIXED, 20, None),
    ("capture_thief", FieldKind.FIXED, 5, None),
    ("survival_cop", FieldKind.FIXED, 5, None),
    ("survival_thief", FieldKind.FIXED, 10, None),
    # Scent / pheromone model
    ("scent_center", FieldKind.FIXED, 0.9, None),
    ("scent_decay", FieldKind.FIXED, 0.10, None),
    ("scent_field_size", FieldKind.FIXED, 5, None),
]

# Build lookup dicts for fast access
_KIND: dict[str, FieldKind] = {name: kind for name, kind, _, _ in _FIELD_SPECS}
_FIXED_VALUE: dict[str, Any] = {
    name: val for name, kind, val, _ in _FIELD_SPECS if kind == FieldKind.FIXED
}
_MIN_VALUE: dict[str, Any] = {
    name: mn for name, kind, _, mn in _FIELD_SPECS if kind == FieldKind.MINIMUM
}
_ALL_FIELDS: frozenset[str] = frozenset(name for name, _, _, _ in _FIELD_SPECS)


def _canonical_json(obj: dict) -> str:
    """Canonical JSON — sorted keys, compact separators."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class CanonicalConfig(CanonicalConfigViewsMixin):
    """Immutable, validated, content-addressed game configuration.

    Usage::

        cfg = CanonicalConfig.from_dict({
            "grid_size": 7,
            "max_barriers": 14,
            ...
        })
        print(cfg.config_sha256)   # 64-char hex
        print(cfg.grid_size)       # 7
        print(cfg.kind("grid_size"))  # FieldKind.MINIMUM
    """

    def __init__(self, fields: dict[str, Any]) -> None:
        """Validate and freeze *fields*.  Raises ConfigError on any violation."""
        errors: list[str] = []

        # Check mandatory fields present
        missing = _ALL_FIELDS - fields.keys()
        if missing:
            errors.append(f"Missing mandatory fields: {sorted(missing)}")

        # Check FIXED fields
        for name, expected in _FIXED_VALUE.items():
            if name in fields and fields[name] != expected:
                errors.append(f"FIXED field '{name}' must be {expected!r}, got {fields[name]!r}")

        # Check MINIMUM fields
        for name, minimum in _MIN_VALUE.items():
            if name in fields and fields[name] < minimum:
                errors.append(f"MINIMUM field '{name}' must be >= {minimum}, got {fields[name]!r}")

        if errors:
            raise ConfigError(
                "Canonical config violations:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        self._fields: dict[str, Any] = dict(fields)
        # SHA-256 over all fields (only the recognised Appendix-F keys)
        canonical_fields = {k: self._fields[k] for k in sorted(_ALL_FIELDS) if k in self._fields}
        self._sha256: str = hashlib.sha256(
            _canonical_json(canonical_fields).encode("utf-8")
        ).hexdigest()

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @property
    def config_sha256(self) -> str:
        """SHA-256 of canonical JSON of all Appendix-F fields."""
        return self._sha256

    def kind(self, field: str) -> FieldKind:
        """Return the FieldKind metadata for *field*."""
        if field not in _KIND:
            raise KeyError(f"Unknown config field: {field!r}")
        return _KIND[field]

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in _ALL_FIELDS:
            return self._fields[name]
        raise AttributeError(f"CanonicalConfig has no field {name!r}")
