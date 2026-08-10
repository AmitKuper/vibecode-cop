"""ProtocolUnderstandingAgent: LLM-based pre-game protocol mapping.

Called ONCE before play begins to produce a ProtocolMappingPlan.
During gameplay only the DeterministicProtocolAdapter (no LLM) is used.

The agent receives:
- canonical local game protocol specification
- remote schemas/descriptions (sanitized for prompt injection)
- placeholder examples (no real secrets or nonces)

It must NOT receive: shared secret, private signing key, real nonce, real commitment.
"""

from __future__ import annotations

import logging
from typing import Any

from cop_worker.protocol.introspector import IntrospectionResult
from cop_worker.protocol.mapping_plan import (
    CompatibilityVerdict,
    ProtocolMappingPlan,
)
from cop_worker.protocol.protocol_agent_fields import ProtocolAgentFieldsMixin
from cop_worker.protocol.protocol_agent_llm import ProtocolAgentLLMMixin
from cop_worker.protocol.protocol_agent_spec import (  # noqa: F401  (re-exports)
    _CANONICAL_PROTOCOL_SPEC,
    _PLACEHOLDER_EXAMPLES,
)
from cop_worker.protocol.schema_mapper import infer_mapping_plan

logger = logging.getLogger(__name__)


class ProtocolUnderstandingAgent(ProtocolAgentLLMMixin, ProtocolAgentFieldsMixin):
    """Pre-game agent that produces a ProtocolMappingPlan via one LLM call.

    Uses deterministic schema inference first and fails closed when neither the
    schema nor the optional pre-game LLM can prove compatibility.
    """

    def __init__(self, llm: Any = None, model_id: str = "unknown") -> None:
        self._llm = llm
        self._model_id = model_id

    def create_plan(self, introspection: IntrospectionResult) -> ProtocolMappingPlan:
        """Produce a ProtocolMappingPlan for the given remote server."""
        if not introspection.tools:
            return ProtocolMappingPlan(
                remote_tool_name="",
                remote_server_name=introspection.server_name,
                remote_schema_digest=introspection.schema_digest,
                capability_gaps=["no MCP tools discovered"],
                verdict=CompatibilityVerdict.INCOMPATIBLE,
                confidence=0.0,
                agent_model="deterministic-schema-agent",
            )

        signed_envelope = self._signed_envelope_plan(introspection)
        if signed_envelope is not None:
            logger.info("ProtocolAgent: verified canonical signed-envelope schema")
            return signed_envelope

        deterministic = self._heuristic_plan(introspection)
        if deterministic.is_compatible() or self._llm is None:
            return deterministic

        try:
            return self._llm_plan(introspection)
        except Exception as exc:
            logger.warning(
                "ProtocolAgent: LLM plan failed (%s); retaining verified schema verdict", exc
            )
            return deterministic

    def _heuristic_plan(self, intro: IntrospectionResult) -> ProtocolMappingPlan:
        """Build a typed plan from all advertised tool schemas."""
        signed_envelope = self._signed_envelope_plan(intro)
        if signed_envelope is not None:
            return signed_envelope
        return infer_mapping_plan(intro)

    @staticmethod
    def _signed_envelope_plan(intro: IntrospectionResult) -> ProtocolMappingPlan | None:
        """Recognize the course's protected HMAC envelope from its schemas."""
        action = intro.get_tool("action")
        start = intro.get_tool("start_game")
        if action is not None:
            action_props = action.input_schema.get("properties", {})
            start_props = start.input_schema.get("properties", {}) if start else {}
            envelope = {"game_id", "message_json", "signature"}.issubset(action_props)
            signed_start = start is not None and {"message_json", "signature"}.issubset(start_props)
            if envelope and signed_start:
                plan = ProtocolMappingPlan.signed_envelope_plan(
                    schema_digest=intro.schema_digest,
                    server_name=intro.server_name,
                    action_tool=action.name,
                    start_tool=start.name,
                )
                conformance = next(
                    (
                        tool.name
                        for tool in intro.tools
                        if "conformance" in f"{tool.name} {tool.description}".lower()
                    ),
                    "",
                )
                plan.conformance_tool = conformance
                return plan
        return None
