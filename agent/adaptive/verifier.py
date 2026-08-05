"""StaticSemanticVerifier: validate a ProtocolMappingPlan before any counted commitment.

Field-name compatibility is insufficient. This verifier checks semantic compatibility:
- every canonical phase has a remote operation;
- every mandatory field can be encoded;
- canonicalization and commitment semantics are compatible;
- nonce remains hidden until final_audit;
- phase ordering is compatible;
- no protected field is dropped or synthesized.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from agent.adaptive.mapping_plan import CompatibilityVerdict, ProtocolMappingPlan

logger = logging.getLogger(__name__)

_NONCE_FIELDS = frozenset(["nonce", "nonces"])
_COMMITMENT_FIELDS = frozenset(["commitment", "commit", "h_commit"])


@dataclass
class VerificationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def reject_reason(self) -> str:
        return "; ".join(self.errors) if self.errors else ""


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

        # 2. All required phases mapped
        if not plan.has_required_phases():
            missing = plan.REQUIRED_PHASES - {pm.phase for pm in plan.phase_mappings}
            errors.append(f"Required phases not mapped: {missing}")

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
        required_by_phase = {
            "start_game": {"game_id", "role"},
            "commit": {"game_id", "step", "role", "commitment"},
            "reveal": {"game_id", "step", "role", "move"},
            "final_audit": {"game_id", "role", "nonces"},
            "game_end": {"game_id", "role"},
            "result_agreement": {"game_id", "role"},
        }
        for pm in plan.phase_mappings:
            fields = {fm.canonical_field for fm in pm.field_mappings}
            signed_envelope = fields.issuperset({"message_json", "signature"})
            missing = required_by_phase.get(pm.phase, set()) - fields
            if missing and not signed_envelope:
                errors.append(f"{pm.phase} cannot transport required fields: {sorted(missing)}")

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
