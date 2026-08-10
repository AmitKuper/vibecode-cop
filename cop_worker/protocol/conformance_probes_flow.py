"""Protocol-flow probes: phase ordering, idempotency, placeholder commit/reveal
(mixin)."""

from __future__ import annotations

import logging

from cop_worker.protocol.conformance_types import (
    _PLACEHOLDER_GAME_ID,
    ProbeOutcome,
    _signed_placeholder_envelope,
)
from cop_worker.protocol.mapping_plan import ProtocolMappingPlan

logger = logging.getLogger(__name__)


class ConformanceFlowProbesMixin:
    """Probes for ordering, idempotency, and the placeholder round trip."""

    def _probe_phase_ordering(self) -> ProbeOutcome:
        """Verify all required phases can be instantiated."""
        for phase in ProtocolMappingPlan.REQUIRED_PHASES:
            pm = next((p for p in self._plan.phase_mappings if p.phase == phase), None)
            if not pm:
                return ProbeOutcome(
                    "phase_ordering", False, error=f"Required phase {phase!r} not in plan"
                )
        return ProbeOutcome("phase_ordering", True, notes="All required phases present")

    def _probe_idempotency_structure(self) -> ProbeOutcome:
        """Verify that adapting the same message twice produces the same result."""
        canonical = _signed_placeholder_envelope(
            {
                "game_id": _PLACEHOLDER_GAME_ID,
                "step": 1,
                "role": "cop",
                "phase": "commit",
                "commitment": "idempotency_test_hash",
                "config_sha256": "config_test",
                "timestamp": "2026-01-01T00:00:00Z",
            }
        )
        try:
            r1 = self._adapter.adapt_request("commit", canonical)
            r2 = self._adapter.adapt_request("commit", canonical)
            if r1.params != r2.params:
                return ProbeOutcome(
                    "idempotency_structure",
                    False,
                    error="Non-deterministic adapter: same input produced different outputs",
                )
        except Exception as exc:
            return ProbeOutcome("idempotency_structure", False, error=str(exc))

        return ProbeOutcome("idempotency_structure", True, notes="Adapter is deterministic")

    def _probe_placeholder_commit_reveal(self) -> ProbeOutcome:
        """Full placeholder commit → reveal without any real secrets."""
        commit_msg = _signed_placeholder_envelope(
            {
                "game_id": _PLACEHOLDER_GAME_ID,
                "step": 1,
                "role": "cop",
                "phase": "commit",
                "commitment": "probe_commit_hash_" + "b" * 40,
                "hint": "I am watching you.",
                "config_sha256": "probe_config_sha",
                "timestamp": "2026-01-01T00:00:00Z",
            }
        )
        reveal_msg = _signed_placeholder_envelope(
            {
                "game_id": _PLACEHOLDER_GAME_ID,
                "step": 1,
                "role": "cop",
                "phase": "reveal",
                "move": "N",
                "config_sha256": "probe_config_sha",
                "timestamp": "2026-01-01T00:00:01Z",
            }
        )
        try:
            c = self._adapter.adapt_request("commit", commit_msg)
            r = self._adapter.adapt_request("reveal", reveal_msg)
            if not c.params or not r.params:
                return ProbeOutcome("placeholder_commit_reveal", False, error="Empty params")
            # Verify no real nonce appeared
            all_values = str(c.params) + str(r.params)
            if "real_nonce" in all_values or "private_key" in all_values:
                return ProbeOutcome(
                    "placeholder_commit_reveal",
                    False,
                    error="Leaked protected value in probe output",
                )
        except Exception as exc:
            return ProbeOutcome("placeholder_commit_reveal", False, error=str(exc))

        return ProbeOutcome(
            "placeholder_commit_reveal", True, notes="Placeholder commit/reveal structure validated"
        )
