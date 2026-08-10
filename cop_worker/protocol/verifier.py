"""StaticSemanticVerifier: validate a ProtocolMappingPlan before any counted commitment.

Field-name compatibility is insufficient — semantic checks:
- every canonical phase has a remote operation;
- every mandatory field can be encoded;
- canonicalization and commitment semantics are compatible;
- nonce hidden until final_audit; phase ordering compatible; no protected field
  dropped or synthesized.
"""

from __future__ import annotations

import logging
from collections import Counter

from cop_worker.protocol.mapping_plan import CompatibilityVerdict, ProtocolMappingPlan
from cop_worker.protocol.verifier_types import (  # noqa: F401  (public re-exports)
    _COMMITMENT_FIELDS,
    _NONCE_FIELDS,
    _REQUIRED_BY_PHASE,
    VerificationResult,
)

logger = logging.getLogger(__name__)


class StaticSemanticVerifier:
    """Verify a ProtocolMappingPlan is semantically compatible before gameplay."""

    def verify(self, plan: ProtocolMappingPlan) -> VerificationResult:
        errors: list[str] = []
        warnings: list[str] = []

        # 1. Verdict check
        if plan.verdict != CompatibilityVerdict.COMPATIBLE:
            errors.append(f"Plan verdict is {plan.verdict.value}: {plan.capability_gaps}")
        if plan.capability_gaps:
            errors.append(f"Unresolved capability gaps: {plan.capability_gaps}")
        if not plan.conformance_tool:
            errors.append("No side-effect-free remote conformance tool is mapped")

        # 2. All required phases mapped
        if not plan.has_required_phases():
            missing = plan.REQUIRED_PHASES - {pm.phase for pm in plan.phase_mappings}
            errors.append(f"Required phases not mapped: {missing}")
        phase_counts = Counter(mapping.phase for mapping in plan.phase_mappings)
        duplicates = sorted(phase for phase, count in phase_counts.items() if count != 1)
        if duplicates:
            errors.append(f"Each required phase must have exactly one mapping: {duplicates}")
        unexpected = set(phase_counts) - plan.REQUIRED_PHASES
        if unexpected:
            errors.append(f"Unknown mapped phases: {sorted(unexpected)}")

        # 3. Commitment binding: commit phase must have a commitment field
        commit_pm = next((pm for pm in plan.phase_mappings if pm.phase == "commit"), None)
        if commit_pm:
            has_commitment = any(
                fm.canonical_field in _COMMITMENT_FIELDS or fm.remote_field in _COMMITMENT_FIELDS
                for fm in commit_pm.field_mappings
            )
            signed_envelope = {fm.canonical_field for fm in commit_pm.field_mappings}.issuperset(
                {"message_json", "signature"}
            )
            if not has_commitment and not signed_envelope:
                errors.append("commit phase has no commitment field — cannot bind commit-reveal")

        # 3B. Each security-critical phase must carry its semantic payload or a
        # complete signed canonical envelope.
        for pm in plan.phase_mappings:
            fields = {fm.canonical_field for fm in pm.field_mappings}
            signed_envelope = fields.issuperset({"message_json", "signature"})
            missing = _REQUIRED_BY_PHASE.get(pm.phase, set()) - fields
            if missing and not signed_envelope:
                errors.append(f"{pm.phase} cannot transport required fields: {sorted(missing)}")
            required_mappings = {
                item.canonical_field for item in pm.field_mappings if item.required
            }
            mandatory = _REQUIRED_BY_PHASE.get(pm.phase, set())
            optionalized = (mandatory - {"signature"}) - required_mappings
            if optionalized and not signed_envelope:
                errors.append(f"{pm.phase} optionalizes protected fields: {sorted(optionalized)}")

            response_keys = set(pm.response_extraction)
            missing_response = set(pm.required_response_fields) - response_keys
            if missing_response:
                errors.append(
                    f"{pm.phase} lacks required response bindings: {sorted(missing_response)}"
                )
            if not pm.idempotent:
                errors.append(f"{pm.phase} does not guarantee idempotent retry")
            if not pm.expected_errors:
                errors.append(f"{pm.phase} does not declare expected error behavior")

        # 4. Nonce must NOT appear in commit or reveal phases (only final_audit)
        for pm in plan.phase_mappings:
            if pm.phase in ("commit", "reveal"):
                has_nonce = any(
                    fm.canonical_field in _NONCE_FIELDS or fm.remote_field in _NONCE_FIELDS
                    for fm in pm.field_mappings
                    if not fm.constant_value
                )
                if has_nonce:
                    errors.append(
                        f"nonce found in {pm.phase} phase — nonce must be secret until final_audit"
                    )

        # 5. Protected fields must map to themselves (no synonym/transform)
        protected = {"game_id", "commitment", "signature", "config_sha256"}
        for pm in plan.phase_mappings:
            for fm in pm.field_mappings:
                if fm.canonical_field in protected and (
                    fm.transform not in ("identity", "rename") and fm.transform != ""
                ):
                    errors.append(
                        f"Protected field {fm.canonical_field!r} has non-identity "
                        f"transform {fm.transform!r} in phase {pm.phase!r}"
                    )

        # 6. No unresolved questions for mandatory phases
        if plan.unresolved_questions:
            warnings.append(f"Unresolved questions: {plan.unresolved_questions}")
            errors.append("Mandatory protocol semantics remain unresolved")

        # One remote tool may serve multiple phases only when the plan proves a
        # phase discriminator or a complete signed canonical envelope.
        tool_counts = Counter(mapping.remote_tool for mapping in plan.phase_mappings)
        for mapping in plan.phase_mappings:
            if tool_counts[mapping.remote_tool] <= 1:
                continue
            fields = {item.canonical_field for item in mapping.field_mappings}
            discriminator = "phase" in fields or fields.issuperset({"message_json", "signature"})
            if not mapping.multiphase_envelope or not discriminator:
                errors.append(
                    f"tool {mapping.remote_tool!r} reuses phases without a proven envelope"
                )
                break

        # 7. Low confidence warning
        if plan.confidence < 0.7:
            errors.append(f"Low mapping confidence: {plan.confidence:.2f}")

        passed = len(errors) == 0
        if not passed:
            logger.error("StaticSemanticVerifier FAILED: %s", errors)
        elif warnings:
            logger.warning("StaticSemanticVerifier warnings: %s", warnings)
        else:
            logger.info("StaticSemanticVerifier PASSED")

        return VerificationResult(passed=passed, errors=errors, warnings=warnings)
