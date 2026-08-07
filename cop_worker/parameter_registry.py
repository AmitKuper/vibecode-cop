"""Parameter registry — authoritative source for all game term specs."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class TermStatus(StrEnum):
    """Authority level of a game term."""

    FIXED = "FIXED"  # must equal exact value; deviation → reject
    MINIMUM = "MINIMUM"  # must be >= required_value; lower → reject
    NEGOTIATED = "NEGOTIATED"  # both peers explicitly agree


@dataclass
class ParameterSpec:
    """Specification for a single game term."""

    name: str
    status: TermStatus
    required_value: Any = None
    default: Any = None


PARAMETER_REGISTRY: list[ParameterSpec] = [
    ParameterSpec("board_size", TermStatus.MINIMUM, required_value=7),
    ParameterSpec("smell_grid_size", TermStatus.FIXED, required_value=5),
    ParameterSpec("decay_per_step", TermStatus.FIXED, required_value=0.1),
    ParameterSpec("emit_intensity", TermStatus.FIXED, required_value=0.9),
    ParameterSpec("max_steps", TermStatus.MINIMUM, required_value=35),
    ParameterSpec("survival_threshold", TermStatus.MINIMUM, required_value=35),
    ParameterSpec("barriers_max", TermStatus.MINIMUM, required_value=14),
    ParameterSpec("num_games", TermStatus.FIXED, required_value=6),
    ParameterSpec("setting", TermStatus.NEGOTIATED, default="Haifa"),
    ParameterSpec("hint_max_words", TermStatus.NEGOTIATED, default=15),
    ParameterSpec("axis_origin_corner", TermStatus.NEGOTIATED, default="top-left"),
    ParameterSpec("axis_start_index", TermStatus.NEGOTIATED, default=0),
    ParameterSpec("thief_start", TermStatus.NEGOTIATED, default=[3, 3]),
    ParameterSpec("cop_start", TermStatus.NEGOTIATED, default=[0, 0]),
    ParameterSpec("response_timeout", TermStatus.NEGOTIATED, default=30),
    ParameterSpec("retry_delay", TermStatus.NEGOTIATED, default=5),
    ParameterSpec("retry_count", TermStatus.NEGOTIATED, default=3),
    ParameterSpec("watchdog_threshold", TermStatus.NEGOTIATED, default=60),
]


def validate_terms(proposed_terms: dict) -> list[str]:
    """Validate proposed_terms against registry. Returns list of violation strings."""
    violations = []
    for spec in PARAMETER_REGISTRY:
        val = proposed_terms.get(spec.name)
        if val is None:
            if spec.status in (TermStatus.FIXED, TermStatus.MINIMUM):
                violations.append(f"{spec.name}: required but missing")
            continue
        if spec.status == TermStatus.FIXED and val != spec.required_value:
            violations.append(f"{spec.name}: must be {spec.required_value!r}, got {val!r}")
        if spec.status == TermStatus.MINIMUM and val < spec.required_value:
            violations.append(f"{spec.name}: must be >= {spec.required_value}, got {val}")
    return violations


def get_defaults() -> dict:
    """Return a dict of all NEGOTIATED term defaults."""
    return {
        spec.name: spec.default
        for spec in PARAMETER_REGISTRY
        if spec.status == TermStatus.NEGOTIATED and spec.default is not None
    }
