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

import json
import logging
import re
from typing import Any

from agent.adaptive.introspector import IntrospectionResult
from agent.adaptive.mapping_plan import (
    CompatibilityVerdict,
    FieldMapping,
    PhaseMapping,
    ProtocolMappingPlan,
)

logger = logging.getLogger(__name__)

_CANONICAL_PROTOCOL_SPEC = """
Canonical CopThief MCP Protocol — local specification

REQUIRED PHASES:
  start_game  — begin a gamelet; fields: game_id, gamelet, role, config_sha256, timestamp
  commit      — commit to a move; fields: game_id, step, role, commitment
                (H(move||nonce||game_id...)), config_sha256, timestamp, hint (optional)
  reveal      — reveal move; fields: game_id, step, role, move (N/S/E/W/STAY or PLACE_*),
                nonce (only at final_audit), config_sha256, timestamp
  final_audit — bilateral audit; fields: game_id, step, role, nonces (dict step→nonce),
                config_sha256, timestamp
  result_agreement — signed result; fields: game_id, role, result_hash, signed_agreement

PROTECTED FIELDS (must not be mutated by mapping):
  game_id, gamelet, step, role, commitment, signature, config_sha256, nonces

BINDING RULES:
  - nonce is secret until final_audit
  - commitment = SHA-256(canonical_message_bytes)
  - phase ordering: start_game → (commit → reveal)* → final_audit → result_agreement
  - no canonicalization change is allowed mid-series
"""

_PLACEHOLDER_EXAMPLES = """
Example commit request (placeholder values — not real):
  {"game_id": "GAME_EXAMPLE_001", "step": 1, "role": "cop",
   "commitment": "abc123def456...", "config_sha256": "sha256placeholder",
   "timestamp": "2026-01-01T00:00:00Z", "hint": "I am heading north."}

Example reveal request:
  {"game_id": "GAME_EXAMPLE_001", "step": 1, "role": "cop",
   "move": "N", "config_sha256": "sha256placeholder",
   "timestamp": "2026-01-01T00:00:00Z"}
"""


class ProtocolUnderstandingAgent:
    """Pre-game agent that produces a ProtocolMappingPlan via one LLM call.

    Falls back to native identity mapping if no LLM is available or LLM fails.
    """

    def __init__(self, llm: Any = None, model_id: str = "unknown") -> None:
        self._llm = llm
        self._model_id = model_id

    def create_plan(self, introspection: IntrospectionResult) -> ProtocolMappingPlan:
        """Produce a ProtocolMappingPlan for the given remote server."""
        if not introspection.tools:
            logger.info("ProtocolAgent: no tools discovered, using native identity plan")
            return ProtocolMappingPlan.native_plan(server_name=introspection.server_name)

        if self._llm is None:
            logger.info("ProtocolAgent: no LLM, using heuristic plan")
            return self._heuristic_plan(introspection)

        try:
            return self._llm_plan(introspection)
        except Exception as exc:
            logger.warning("ProtocolAgent: LLM plan failed (%s), falling back to heuristic", exc)
            return self._heuristic_plan(introspection)

    def _heuristic_plan(self, intro: IntrospectionResult) -> ProtocolMappingPlan:
        """Deterministic heuristic: look for action-like tools by name."""
        action = intro.get_tool("action")
        start = intro.get_tool("start_game")
        if action is not None:
            action_props = action.input_schema.get("properties", {})
            start_props = start.input_schema.get("properties", {}) if start else {}
            envelope = {"game_id", "message_json", "signature"}.issubset(action_props)
            signed_start = start is not None and {"message_json", "signature"}.issubset(start_props)
            if envelope and signed_start:
                return ProtocolMappingPlan.signed_envelope_plan(
                    schema_digest=intro.schema_digest,
                    server_name=intro.server_name,
                    action_tool=action.name,
                    start_tool=start.name,
                )

        # Find best tool: prefer "action", then anything with "action"/"commit" in name
        tool = (
            intro.get_tool("action")
            or next((t for t in intro.tools if "action" in t.name.lower()), None)
            or next((t for t in intro.tools if "commit" in t.name.lower()), None)
            or (intro.tools[0] if intro.tools else None)
        )
        if not tool:
            return ProtocolMappingPlan.native_plan(server_name=intro.server_name)

        # Determine field mapping from remote schema
        props = tool.input_schema.get("properties", {})
        phase_mappings = []
        for phase in ProtocolMappingPlan.REQUIRED_PHASES:
            fms = self._map_canonical_fields(phase, props)
            phase_mappings.append(
                PhaseMapping(
                    phase=phase,
                    remote_tool=tool.name,
                    field_mappings=fms,
                    response_extraction={"ok": "ok", "phase": "phase", "winner": "winner"},
                    notes=f"heuristic mapping for {phase}",
                )
            )

        verdict = CompatibilityVerdict.COMPATIBLE
        gaps: list[str] = []

        # Check for mandatory semantic compatibility
        if "commitment" not in props and "commit" not in str(props):
            gaps.append("no commitment field found")
            verdict = CompatibilityVerdict.INCOMPATIBLE

        return ProtocolMappingPlan(
            remote_tool_name=tool.name,
            remote_server_name=intro.server_name,
            remote_schema_digest=intro.schema_digest,
            phase_mappings=phase_mappings,
            capability_gaps=gaps,
            verdict=verdict,
            confidence=0.8,
            agent_model="heuristic",
            agent_version="1.0",
        )

    def _map_canonical_fields(self, phase: str, props: dict) -> list[FieldMapping]:
        """Map canonical fields to remote props by name matching."""
        canonical = ["game_id", "step", "role", "phase", "config_sha256", "timestamp"]
        if phase == "commit":
            canonical += ["commitment", "hint"]
        elif phase == "reveal":
            canonical += ["move"]
        elif phase == "final_audit":
            canonical += ["nonces"]
        elif phase == "result_agreement":
            canonical += ["result_hash", "signed_agreement"]

        fms = []
        for cf in canonical:
            remote = cf if cf in props else self._closest_match(cf, props)
            if remote:
                fms.append(
                    FieldMapping(
                        canonical_field=cf,
                        remote_field=remote,
                        required=(cf in {"game_id", "step", "role", "commitment", "move"}),
                    )
                )
        return fms

    def _llm_plan(self, intro: IntrospectionResult) -> ProtocolMappingPlan:
        """Call LLM once to produce a structured mapping plan."""
        tools_desc = "\n".join(
            f"  Tool: {t.name}\n  Description: {t.description[:200]}\n"
            f"  Schema: {json.dumps(t.input_schema, indent=2)[:500]}"
            for t in intro.tools
        )

        prompt = (
            f"You are mapping a remote MCP game server protocol to a canonical game protocol.\n\n"
            f"=== CANONICAL PROTOCOL ===\n{_CANONICAL_PROTOCOL_SPEC}\n\n"
            f"=== REMOTE SERVER: {intro.server_name} (v{intro.server_version}) ===\n"
            f"Remote tools:\n{tools_desc}\n\n"
            f"=== PLACEHOLDER EXAMPLES ===\n{_PLACEHOLDER_EXAMPLES}\n\n"
            "Output a JSON object with these fields:\n"
            "{\n"
            '  "remote_tool_name": "...",\n'
            '  "verdict": "COMPATIBLE" or "INCOMPATIBLE",\n'
            '  "confidence": 0.0-1.0,\n'
            '  "capability_gaps": [],\n'
            '  "unresolved_questions": [],\n'
            '  "field_renames": {"canonical_field": "remote_field", ...}\n'
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

    def _build_plan_from_llm(self, parsed: dict, intro: IntrospectionResult) -> ProtocolMappingPlan:
        verdict = CompatibilityVerdict(parsed.get("verdict", "COMPATIBLE"))
        renames: dict[str, str] = parsed.get("field_renames", {})
        tool_name: str = parsed.get("remote_tool_name", "action")
        tool = intro.get_tool(tool_name) or (intro.tools[0] if intro.tools else None)
        if not tool:
            return ProtocolMappingPlan.native_plan(server_name=intro.server_name)

        props = tool.input_schema.get("properties", {})
        phase_mappings = []
        for phase in ProtocolMappingPlan.REQUIRED_PHASES:
            fms = []
            for cf in self._canonical_fields_for_phase(phase):
                remote = renames.get(cf, cf if cf in props else self._closest_match(cf, props))
                if remote:
                    fms.append(
                        FieldMapping(
                            canonical_field=cf,
                            remote_field=remote,
                            required=(cf in {"game_id", "step", "role", "commitment", "move"}),
                        )
                    )
            phase_mappings.append(
                PhaseMapping(
                    phase=phase,
                    remote_tool=tool_name,
                    field_mappings=fms,
                    response_extraction={"ok": "ok", "phase": "phase"},
                )
            )

        return ProtocolMappingPlan(
            remote_tool_name=tool_name,
            remote_server_name=intro.server_name,
            remote_schema_digest=intro.schema_digest,
            phase_mappings=phase_mappings,
            capability_gaps=parsed.get("capability_gaps", []),
            unresolved_questions=parsed.get("unresolved_questions", []),
            verdict=verdict,
            confidence=float(parsed.get("confidence", 0.9)),
            agent_model=self._model_id,
            agent_version="1.0",
        )

    def _canonical_fields_for_phase(self, phase: str) -> list[str]:
        base = ["game_id", "step", "role", "phase", "config_sha256", "timestamp"]
        extras = {
            "commit": ["commitment", "hint"],
            "reveal": ["move"],
            "final_audit": ["nonces"],
            "result_agreement": ["result_hash", "signed_agreement"],
        }
        return base + extras.get(phase, [])

    @staticmethod
    def _closest_match(field: str, props: dict) -> str | None:
        if not props:
            return None
        # Exact match
        if field in props:
            return field
        # Prefix/suffix match
        for key in props:
            if field in key or key in field:
                return key
        return None
