"""DeterministicProtocolAdapter: apply a ProtocolMappingPlan during gameplay.

No LLM is called during gameplay. All mapping is performed by the DSL engine.
Protected values (game_id, signature, commitment, etc.) are verified byte-for-byte.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass

from league_manager.protocol.dsl import AdapterDSL
from league_manager.protocol.mapping_plan import PhaseMapping, ProtocolMappingPlan

logger = logging.getLogger(__name__)

# Fields that must not be modified by DSL mapping
_PROTECTED_FIELDS = frozenset(
    [
        "game_id",
        "gamelet",
        "step",
        "role",
        "commitment",
        "signature",
        "config_sha256",
        "declaration_hash",
        "protocol_hash",
        "nonces",
        "message_json",
    ]
)


@dataclass
class AdaptedRequest:
    tool_name: str
    params: dict
    phase: str
    request_digest: str


@dataclass
class AdaptedResponse:
    phase: str
    extracted: dict
    raw: dict
    response_digest: str


class ProtocolCompatibilityError(Exception):
    """Raised when a remote protocol cannot be adapted safely."""


class DeterministicProtocolAdapter:
    """Applies a frozen ProtocolMappingPlan deterministically during gameplay.

    Per-turn behavior:
    - Look up PhaseMapping for the requested phase
    - Apply DSL field_mappings to the canonical message
    - Inject protected values after mapping
    - Verify protected fields were not corrupted
    - Call the remote tool
    - Extract response fields via response_extraction map
    - Validate response schema
    - Return AdaptedResponse

    No LLM is called at any point during gameplay.
    """

    def __init__(self, plan: ProtocolMappingPlan) -> None:
        if not plan.is_compatible():
            raise ProtocolCompatibilityError(
                f"Plan is not compatible: verdict={plan.verdict.value}, gaps={plan.capability_gaps}"
            )
        if not plan.has_required_phases():
            missing = plan.REQUIRED_PHASES - {pm.phase for pm in plan.phase_mappings}
            raise ProtocolCompatibilityError(f"Plan missing required phases: {missing}")
        self._plan = plan
        self._dsl = AdapterDSL()
        self._per_turn_llm_calls = 0

    @property
    def per_turn_llm_calls(self) -> int:
        """Must remain 0 during gameplay."""
        return self._per_turn_llm_calls

    def adapt_request(
        self,
        phase: str,
        canonical_msg: dict,
        protected_values: dict | None = None,
    ) -> AdaptedRequest:
        """Map a canonical message to the remote tool call params."""
        pm = self._get_phase_mapping(phase)
        canonical = dict(canonical_msg)
        prot = self._extract_protected(canonical, protected_values)
        canonical.update(prot)

        params = self._dsl.map_message(
            canonical_msg=canonical,
            field_mappings=pm.field_mappings,
            protected_values=None,
        )

        # Protected values may be renamed or nested by a verified mapping plan,
        # but their byte values may never change.  Do not inject canonical field
        # names at the top level: that breaks remote schemas and can create two
        # conflicting representations of the same cryptographic value.
        for fm in pm.field_mappings:
            if fm.canonical_field not in prot:
                continue
            actual = self._deep_get(params, fm.remote_field)
            expected = AdapterDSL.from_spec(
                [{"name": fm.transform, "args": fm.transform_args}]
                if fm.transform != "identity"
                else []
            ).apply_all(prot[fm.canonical_field])
            if actual != expected:
                raise ProtocolCompatibilityError(
                    f"Protected field {fm.canonical_field!r} was changed while mapping "
                    f"phase {phase!r}"
                )

        # Schema-validate the request
        self._validate_request(params, pm)

        digest = hashlib.sha256(
            json.dumps(params, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

        return AdaptedRequest(
            tool_name=pm.remote_tool,
            params=params,
            phase=phase,
            request_digest=digest,
        )

    def adapt_response(
        self,
        phase: str,
        raw_response: dict,
        expected_protected: dict | None = None,
    ) -> AdaptedResponse:
        """Extract canonical fields from a remote response."""
        pm = self._get_phase_mapping(phase)

        extracted: dict = {}
        for canonical_key, remote_path in pm.response_extraction.items():
            value = AdapterDSL.identity().apply_all(self._deep_get(raw_response, remote_path))
            # A response mapping describes where a field may be found; it must not
            # manufacture a ``None`` value that then overwrites a valid canonical
            # field already present in the raw response.
            if value is not None:
                extracted[canonical_key] = value

        missing_response = [
            key
            for key in pm.required_response_fields
            if extracted.get(key) is None and raw_response.get(key) is None
        ]
        if missing_response:
            raise ProtocolCompatibilityError(
                f"Required response fields missing for {phase!r}: {missing_response}"
            )

        # Verify protected response fields
        if expected_protected:
            for k, expected_v in expected_protected.items():
                actual_v = extracted.get(k)
                if actual_v is None:
                    actual_v = raw_response.get(k)
                if actual_v is None:
                    raise ProtocolCompatibilityError(f"Protected response field {k!r} is missing")
                if actual_v != expected_v:
                    raise ProtocolCompatibilityError(
                        f"Protected response field {k!r} mismatch: "
                        f"expected {expected_v!r}, got {actual_v!r}"
                    )

        digest = hashlib.sha256(
            json.dumps(raw_response, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

        return AdaptedResponse(
            phase=phase,
            extracted=extracted,
            raw=raw_response,
            response_digest=digest,
        )

    def check_schema_digest(self, current_digest: str) -> bool:
        """Verify remote schema hasn't changed mid-series."""
        ok = current_digest == self._plan.remote_schema_digest
        if not ok:
            logger.error(
                "DeterministicAdapter: schema digest changed mid-series! expected=%s actual=%s",
                self._plan.remote_schema_digest,
                current_digest,
            )
        return ok

    def _get_phase_mapping(self, phase: str) -> PhaseMapping:
        for pm in self._plan.phase_mappings:
            if pm.phase == phase:
                return pm
        raise ProtocolCompatibilityError(f"No mapping for phase {phase!r}")

    def _extract_protected(
        self,
        canonical_msg: dict,
        extra: dict | None,
    ) -> dict:
        result = {k: v for k, v in canonical_msg.items() if k in _PROTECTED_FIELDS}
        if extra:
            result.update(extra)
        return result

    def _validate_request(self, params: dict, pm: PhaseMapping) -> None:
        required = [fm.remote_field for fm in pm.field_mappings if fm.required]
        missing = [f for f in required if self._deep_get(params, f) is None]
        if missing:
            raise ProtocolCompatibilityError(
                f"DeterministicAdapter: required fields missing in request: {missing}"
            )

    @staticmethod
    def _deep_get(d: dict, path: str) -> object:
        """Traverse dot-separated path."""
        value: object = d
        for key in path.split("."):
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value

    @classmethod
    def native(cls) -> DeterministicProtocolAdapter:
        """Identity adapter for a native server with canonical `action` tool."""
        return cls(ProtocolMappingPlan.native_plan())
