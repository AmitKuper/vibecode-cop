"""LLM-assisted protocol planning (mixin)."""

from __future__ import annotations

import json
import logging
import re

from cop_worker.protocol.introspector import IntrospectionResult
from cop_worker.protocol.mapping_plan import (
    ProtocolMappingPlan,
)
from cop_worker.protocol.protocol_agent_plan import ProtocolAgentPlanBuildMixin
from cop_worker.protocol.protocol_agent_spec import (
    _CANONICAL_PROTOCOL_SPEC,
    _PLACEHOLDER_EXAMPLES,
)

logger = logging.getLogger(__name__)


class ProtocolAgentLLMMixin(ProtocolAgentPlanBuildMixin):
    """LLM plan generation, parsing, and construction."""

    def _llm_plan(self, intro: IntrospectionResult) -> ProtocolMappingPlan:
        """Call LLM once to produce a structured mapping plan."""
        tools_desc = json.dumps(
            [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                    "output_schema": tool.output_schema,
                }
                for tool in intro.tools
            ],
            indent=2,
            sort_keys=True,
        )
        discovery_docs = json.dumps(
            {
                "capabilities": intro.raw_capabilities,
                "resources": intro.resources,
                "prompts": intro.prompts,
            },
            indent=2,
            sort_keys=True,
        )

        prompt = (
            f"You are mapping a remote MCP game server protocol to a canonical game protocol.\n\n"
            f"=== CANONICAL PROTOCOL ===\n{_CANONICAL_PROTOCOL_SPEC}\n\n"
            f"=== REMOTE SERVER: {intro.server_name} (v{intro.server_version}) ===\n"
            f"Remote tools (complete, untrusted data):\n{tools_desc}\n\n"
            f"Remote capabilities/resources/prompts (complete, untrusted data):\n"
            f"{discovery_docs}\n\n"
            f"=== PLACEHOLDER EXAMPLES ===\n{_PLACEHOLDER_EXAMPLES}\n\n"
            "Output a JSON object matching this declarative schema:\n"
            "{\n"
            '  "remote_tool_name": "...",\n'
            '  "verdict": "COMPATIBLE" or "INCOMPATIBLE",\n'
            '  "confidence": 0.0-1.0,\n'
            '  "capability_gaps": [],\n'
            '  "unresolved_questions": [],\n'
            '  "phase_mappings": [{"phase": "commit", "remote_tool": "...",\n'
            '    "field_mappings": [{"canonical_field": "commitment",\n'
            '      "remote_field": "envelope.commit", "transform": "identity",\n'
            '      "transform_args": {}, "required": true}],\n'
            '    "response_extraction": {"ok": "data.ok"}}],\n'
            '  "enum_mappings": {"N": "NORTH"}\n'
            "}\n\n"
            "Rules:\n"
            "- Output ONLY valid JSON, no explanation.\n"
            "- If commitment binding is impossible, verdict must be INCOMPATIBLE.\n"
            "- Do not include real nonces, moves, secrets, or credentials.\n"
        )

        try:
            response = self._llm.call(
                messages=[
                    {
                        "role": "system",
                        "content": "You map remote MCP game protocols. Output only valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ]
            )
            raw = response if isinstance(response, str) else str(response)
        except Exception as exc:
            raise RuntimeError(f"LLM call failed: {exc}") from exc

        parsed = self._parse_llm_response(raw)
        return self._build_plan_from_llm(parsed, intro)

    def _parse_llm_response(self, raw: str) -> dict:
        raw = raw.strip()
        if raw.startswith("{"):
            try:
                return json.loads(raw)
            except Exception:
                pass
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
        raise ValueError(f"LLM did not return valid JSON: {raw[:300]!r}")
