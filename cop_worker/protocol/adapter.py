"""DeterministicProtocolAdapter: apply a ProtocolMappingPlan during gameplay.

No LLM is called during gameplay. All mapping is performed by the DSL engine.
Protected values (game_id, signature, commitment, etc.) are verified byte-for-byte.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass

from cop_worker.protocol.dsl import AdapterDSL
from cop_worker.protocol.mapping_plan import ProtocolMappingPlan

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


from cop_worker.protocol.adapter_response import AdapterResponseMixin  # noqa: E402


class DeterministicProtocolAdapter(AdapterResponseMixin):
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
