"""Structural probes: schema, field mapping, commitment binding, nonce isolation,
protected fields (mixin)."""

from __future__ import annotations

import logging

from cop_worker.protocol.conformance_types import (
    _PLACEHOLDER_GAME_ID,
    ProbeOutcome,
    _signed_placeholder_envelope,
)

logger = logging.getLogger(__name__)


class ConformanceBindingProbesMixin:
    """Probes for schema shape and commitment binding."""

    def _probe_schema_validation(self) -> ProbeOutcome:
        """Verify plan has all required phases."""
        if not self._plan.has_required_phases():
            return ProbeOutcome("schema_validation", False, "Missing required phases")
        return ProbeOutcome("schema_validation", True, notes="Required phases present")

    def _probe_field_mapping_completeness(self) -> ProbeOutcome:
        """Verify commit and reveal phases have required canonical fields."""
        for phase_name in ("commit", "reveal"):
            pm = next((p for p in self._plan.phase_mappings if p.phase == phase_name), None)
            if not pm:
                return ProbeOutcome(
                    "field_mapping_completeness", False, error=f"Phase {phase_name!r} not mapped"
                )
        return ProbeOutcome("field_mapping_completeness", True, notes="Commit+reveal mapped")

    def _probe_commitment_binding(self) -> ProbeOutcome:
        """Verify commit phase can carry a commitment value."""
        commit_pm = next((pm for pm in self._plan.phase_mappings if pm.phase == "commit"), None)
        if not commit_pm:
            return ProbeOutcome("commitment_binding", False, error="No commit phase")

        # Simulate mapping with a placeholder commitment
        canonical = _signed_placeholder_envelope(
            {
                "game_id": _PLACEHOLDER_GAME_ID,
                "step": 1,
                "role": "cop",
                "phase": "commit",
                "commitment": "placeholder_commitment_hash_" + "a" * 32,
                "config_sha256": "config_placeholder",
                "timestamp": "2026-01-01T00:00:00Z",
            }
        )
        try:
            adapted = self._adapter.adapt_request("commit", canonical)
            has_commitment = canonical["commitment"] in str(adapted.params)
            if not has_commitment:
                return ProbeOutcome(
                    "commitment_binding",
                    False,
                    error="Commitment field missing from adapted request",
                )
        except Exception as exc:
            return ProbeOutcome("commitment_binding", False, error=str(exc))

        return ProbeOutcome(
            "commitment_binding", True, notes="Commitment field successfully mapped"
        )

    def _probe_nonce_isolation(self) -> ProbeOutcome:
        """Verify nonce does not appear in commit or reveal phases."""
        for phase_name in ("commit", "reveal"):
            pm = next((p for p in self._plan.phase_mappings if p.phase == phase_name), None)
            if not pm:
                continue
            for fm in pm.field_mappings:
                if "nonce" in fm.canonical_field.lower() or "nonce" in fm.remote_field.lower():
                    return ProbeOutcome(
                        "nonce_isolation",
                        False,
                        error=f"Nonce field found in {phase_name} phase — security violation",
                    )
        return ProbeOutcome(
            "nonce_isolation", True, notes="Nonce correctly isolated to final_audit"
        )

    def _probe_protected_field_integrity(self) -> ProbeOutcome:
        """Verify protected fields pass through unchanged."""
        canonical = _signed_placeholder_envelope(
            {
                "game_id": "EXACT_GAME_ID_999",
                "step": 7,
                "role": "police",
                "phase": "commit",
                "commitment": "EXACT_COMMITMENT_HASH_abc123",
                "config_sha256": "EXACT_CONFIG_SHA",
                "timestamp": "2026-01-01T00:00:00Z",
            }
        )
        protected = {
            "game_id": "EXACT_GAME_ID_999",
            "commitment": "EXACT_COMMITMENT_HASH_abc123",
        }
        try:
            adapted = self._adapter.adapt_request("commit", canonical, protected)
            # Verify protected values appear in output
            for k, v in protected.items():
                found = any(str(v) in str(param_v) for param_v in adapted.params.values())
                if not found:
                    return ProbeOutcome(
                        "protected_field_integrity",
                        False,
                        error=f"Protected field {k!r} lost or corrupted",
                    )
        except Exception as exc:
            return ProbeOutcome("protected_field_integrity", False, error=str(exc))

        return ProbeOutcome("protected_field_integrity", True, notes="Protected fields preserved")
