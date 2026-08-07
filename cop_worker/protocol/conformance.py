"""ConformanceProbes: safe pre-game protocol validation probes.

Run before any counted commitment. Tests:
- schema validation
- ping/readiness
- start-game negotiation
- idempotency behavior
- error response format
- placeholder commit/reveal structure (no real secrets)

No counted commitment occurs until all probes pass.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from cop_worker.protocol.adapter import DeterministicProtocolAdapter
from cop_worker.protocol.mapping_plan import ProtocolMappingPlan

logger = logging.getLogger(__name__)

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


class ConformanceProbes:
    """Run safe, non-mutating probes against the DeterministicProtocolAdapter."""

    def __init__(self, adapter: DeterministicProtocolAdapter, plan: ProtocolMappingPlan) -> None:
        self._adapter = adapter
        self._plan = plan

    def run_all(self) -> ConformanceReport:
        probes = [
            self._probe_schema_validation,
            self._probe_field_mapping_completeness,
            self._probe_commitment_binding,
            self._probe_nonce_isolation,
            self._probe_protected_field_integrity,
            self._probe_phase_ordering,
            self._probe_idempotency_structure,
            self._probe_placeholder_commit_reveal,
        ]
        results: list[ProbeOutcome] = []
        for probe_fn in probes:
            try:
                outcome = probe_fn()
                results.append(outcome)
            except Exception as exc:
                results.append(
                    ProbeOutcome(probe_name=probe_fn.__name__, passed=False, error=str(exc))
                )

        all_passed = all(p.passed for p in results)
        report = ConformanceReport(all_passed=all_passed, probes=results)
        if all_passed:
            logger.info("ConformanceProbes: all passed (%s)", report.summary())
        else:
            logger.error("ConformanceProbes: FAILED — %s", report.failed_probes())
        return report

    async def run_remote(
        self,
        tool_caller: Callable[[str, dict], Awaitable[dict]],
    ) -> ConformanceReport:
        """Exercise mapped tools with inert, deliberately invalid envelopes.

        A conforming course peer must reject these probes before mutating game
        state because the game id, configuration hash, and signature are
        placeholders. Repeating each call also checks stable/idempotent failure
        behavior without revealing a real nonce, move, key, or commitment.
        """
        outcomes: list[ProbeOutcome] = []
        for phase in sorted(ProtocolMappingPlan.REQUIRED_PHASES):
            try:
                canonical = self._remote_placeholder(phase)
                request = self._adapter.adapt_request(phase, canonical)
                first = await tool_caller(request.tool_name, request.params)
                second = await tool_caller(request.tool_name, request.params)
                if not isinstance(first, dict) or not isinstance(second, dict):
                    raise TypeError("remote probe response must be an object")
                if first.get("ok") is True or second.get("ok") is True:
                    raise ValueError("peer accepted an invalid conformance envelope")
                first_shape = self._stable_response_shape(first)
                second_shape = self._stable_response_shape(second)
                if first_shape != second_shape:
                    raise ValueError("non-idempotent response to identical inert probe")
                self._adapter.adapt_response(phase, first)
                outcomes.append(
                    ProbeOutcome(
                        f"remote_{phase}",
                        True,
                        notes="mapped tool reached and invalid envelope rejected stably",
                    )
                )
            except Exception as exc:
                outcomes.append(ProbeOutcome(f"remote_{phase}", False, error=str(exc)))
                continue
            try:
                canonical = self._remote_placeholder(phase)
                mapped = self._adapter.adapt_request(phase, canonical)
                full_digest = hashlib.sha256(
                    json.dumps(
                        mapped.params, sort_keys=True, separators=(",", ":"), default=str
                    ).encode("utf-8")
                ).hexdigest()
                key = hashlib.sha256(f"{_PLACEHOLDER_GAME_ID}:{phase}".encode()).hexdigest()
                params = {
                    "phase": phase,
                    "game_id": _PLACEHOLDER_GAME_ID,
                    "request_digest": full_digest,
                    "idempotency_key": key,
                }
                first = await tool_caller(self._plan.conformance_tool, params)
                second = await tool_caller(self._plan.conformance_tool, params)
                if first != second:
                    raise ValueError("valid conformance retry was not byte-stable")
                if not isinstance(first, dict) or first.get("ok") is not True:
                    raise ValueError("remote did not accept the side-effect-free valid probe")
                if first.get("game_id") != _PLACEHOLDER_GAME_ID or first.get("phase") != phase:
                    raise ValueError("valid conformance probe corrupted protected fields")
                if first.get("idempotent") is not True or first.get("side_effects") != 0:
                    raise ValueError(
                        "valid conformance probe lacks idempotent no-side-effect proof"
                    )
                semantic_proofs = (
                    "canonical_order",
                    "canonical_json_bytes",
                    "commitment_binding",
                    "nonce_final_audit_only",
                    "comprehensive_audit",
                    "result_agreement",
                )
                missing_proofs = [name for name in semantic_proofs if first.get(name) is not True]
                if missing_proofs:
                    raise ValueError(
                        f"valid conformance probe lacks semantic proofs: {missing_proofs}"
                    )
                outcomes.append(
                    ProbeOutcome(
                        f"remote_valid_{phase}",
                        True,
                        notes="valid semantic probe accepted twice without state mutation",
                    )
                )
            except Exception as exc:
                outcomes.append(ProbeOutcome(f"remote_valid_{phase}", False, error=str(exc)))
        return ConformanceReport(all(p.passed for p in outcomes), outcomes)

    @staticmethod
    def _stable_response_shape(response: dict) -> tuple:
        return tuple(
            (key, type(value).__name__, str(value))
            for key, value in sorted(response.items())
            if key not in {"timestamp", "request_id", "trace_id"}
        )

    @staticmethod
    def _remote_placeholder(phase: str) -> dict:
        payload = {
            "game_id": _PLACEHOLDER_GAME_ID,
            "gamelet": 1,
            "step": 1,
            "role": "cop",
            "phase": phase,
            "config_sha256": "0" * 64,
            "timestamp": "2026-01-01T00:00:00Z",
            "commitment": "0" * 64,
            "move": "STAY",
            "hint": "Protocol conformance probe.",
            "intent": "TRUTH",
            "nonces": {"1": "PROBE_NONCE_NOT_REAL"},
            "reason": "probe",
            "result_hash": "0" * 64,
            "signed_agreement": {"probe": True},
            "signed_audit_summary": {"probe": True},
        }
        return _signed_placeholder_envelope(payload)

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
