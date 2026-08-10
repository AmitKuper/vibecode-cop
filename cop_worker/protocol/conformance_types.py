"""Conformance data types and the placeholder envelope helper."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_PLACEHOLDER_GAME_ID = "PROBE_GAME_" + uuid.uuid4().hex[:8]


_PLACEHOLDER_GAME_ID = "PROBE_GAME_" + uuid.uuid4().hex[:8]


def _signed_placeholder_envelope(message: dict) -> dict:
    """Add inert envelope fields used by signed-wrapper MCP protocols."""
    canonical = json.dumps(message, sort_keys=True, separators=(",", ":"))
    return {**message, "message_json": canonical, "signature": "a" * 64}


@dataclass
class ProbeOutcome:
    probe_name: str
    passed: bool
    error: str = ""
    latency_ms: float = 0.0
    notes: str = ""


@dataclass
class ConformanceReport:
    all_passed: bool
    probes: list[ProbeOutcome] = field(default_factory=list)

    def failed_probes(self) -> list[str]:
        return [p.probe_name for p in self.probes if not p.passed]

    def summary(self) -> str:
        passed = sum(1 for p in self.probes if p.passed)
        return f"{passed}/{len(self.probes)} probes passed"
