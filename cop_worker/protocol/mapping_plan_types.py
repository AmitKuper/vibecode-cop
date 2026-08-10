"""Mapping-plan leaf types: verdict, field and phase mappings."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class CompatibilityVerdict(enum.StrEnum):
    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class FieldMapping:
    """Maps one canonical field to a remote field path, with optional transform."""

    canonical_field: str
    remote_field: str
    transform: str = "identity"
    transform_args: dict = field(default_factory=dict)
    required: bool = True
    constant_value: Any = None


@dataclass
class PhaseMapping:
    """Maps one canonical protocol phase to a remote tool call."""

    phase: str
    remote_tool: str
    field_mappings: list[FieldMapping] = field(default_factory=list)
    response_extraction: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    required_response_fields: list[str] = field(default_factory=lambda: ["ok", "game_id", "phase"])
    expected_errors: list[str] = field(
        default_factory=lambda: ["invalid_signature", "out_of_order", "duplicate_conflict"]
    )
    idempotent: bool = True
    multiphase_envelope: bool = False
