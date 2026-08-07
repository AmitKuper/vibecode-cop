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

from league_manager.protocol.introspector import IntrospectionResult
from league_manager.protocol.mapping_plan import (
    CompatibilityVerdict,
    FieldMapping,
    PhaseMapping,
    ProtocolMappingPlan,
)
from league_manager.protocol.schema_mapper import infer_mapping_plan

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
  audit_summary — signed comprehensive audit summary; fields: game_id, role,
                signed_audit_summary
  game_end — independently checked gamelet outcome; fields: game_id, step, role, reason
  result_agreement — signed result; fields: game_id, role, result_hash, signed_agreement
  abort — controlled technical-loss/abort; fields: game_id, step, role, reason

PROTECTED FIELDS (must not be mutated by mapping):
  game_id, gamelet, step, role, commitment, signature, config_sha256, nonces,
  signed_audit_summary, signed_agreement

BINDING RULES:
  - nonce is secret until final_audit
  - commitment = SHA-256(canonical_message_bytes)
  - phase ordering: start_game → (commit → reveal)* → final_audit → game_end;
    after exactly six gamelets → result_agreement
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

    def _map_canonical_fields(self, phase: str, props: dict) -> list[FieldMapping]:
        """Map canonical fields to remote props by name matching."""
        canonical = [
            "game_id",
            "step",
            "role",
            "phase",
            "config_sha256",
            "timestamp",
            "signature",
        ]
        if phase == "start_game":
            canonical += ["gamelet"]
        elif phase == "commit":
            canonical += ["commitment", "hint"]
        elif phase == "reveal":
            canonical += ["move"]
        elif phase == "final_audit":
            canonical += ["nonces"]
        elif phase == "audit_summary":
            canonical += ["signed_audit_summary"]
        elif phase == "game_end":
            canonical += ["reason"]
        elif phase == "result_agreement":
            canonical += ["result_hash", "signed_agreement"]
        elif phase == "abort":
            canonical += ["reason"]

        fms = []
        for cf in canonical:
            remote = cf if cf in props else self._closest_match(cf, props)
            if remote:
                fms.append(
                    FieldMapping(
                        canonical_field=cf,
                        remote_field=remote,
                        required=cf not in {"timestamp", "hint", "result_hash"},
                    )
                )
        return fms

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

    def _build_plan_from_llm(self, parsed: dict, intro: IntrospectionResult) -> ProtocolMappingPlan:
        if parsed.get("phase_mappings"):
            payload = dict(parsed)
            payload["remote_server_name"] = intro.server_name
            payload["remote_schema_digest"] = intro.schema_digest
            payload["agent_model"] = self._model_id
            payload["agent_version"] = "2.0"
            plan = ProtocolMappingPlan.from_dict(payload)
            self._validate_remote_plan(plan, intro)
            return plan
        verdict = CompatibilityVerdict(parsed.get("verdict", "COMPATIBLE"))
        renames: dict[str, str] = parsed.get("field_renames", {})
        tool_name: str = parsed.get("remote_tool_name", "action")
        tool = intro.get_tool(tool_name) or (intro.tools[0] if intro.tools else None)
        if not tool:
            return ProtocolMappingPlan.native_plan(server_name=intro.server_name)
        tool_name = tool.name

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
                            required=cf not in {"timestamp", "hint", "result_hash"},
                        )
                    )
            phase_mappings.append(
                PhaseMapping(
                    phase=phase,
                    remote_tool=tool_name,
                    field_mappings=fms,
                    response_extraction={"ok": "ok", "game_id": "game_id", "phase": "phase"},
                    multiphase_envelope=any(
                        item.canonical_field in {"phase", "message_json"} for item in fms
                    ),
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

    @staticmethod
    def _validate_remote_plan(plan: ProtocolMappingPlan, intro: IntrospectionResult) -> None:
        tools = {tool.name: tool for tool in intro.tools}
        if plan.conformance_tool not in tools:
            raise ValueError(f"LLM selected unknown conformance tool {plan.conformance_tool!r}")
        for phase in plan.phase_mappings:
            if phase.remote_tool not in tools:
                raise ValueError(f"LLM selected unknown remote tool {phase.remote_tool!r}")
            roots = tools[phase.remote_tool].input_schema.get("properties", {})
            for mapping in phase.field_mappings:
                root = mapping.remote_field.split(".", 1)[0]
                if root not in roots:
                    raise ValueError(
                        f"LLM selected unknown field {mapping.remote_field!r} "
                        f"for tool {phase.remote_tool!r}"
                    )

    def _canonical_fields_for_phase(self, phase: str) -> list[str]:
        base = [
            "game_id",
            "step",
            "role",
            "phase",
            "config_sha256",
            "timestamp",
            "signature",
        ]
        extras = {
            "start_game": ["gamelet"],
            "commit": ["commitment", "hint"],
            "reveal": ["move"],
            "final_audit": ["nonces"],
            "audit_summary": ["signed_audit_summary"],
            "game_end": ["reason"],
            "result_agreement": ["result_hash", "signed_agreement"],
            "abort": ["reason"],
        }
        return base + extras.get(phase, [])

    @staticmethod
    def _closest_match(field: str, props: dict) -> str | None:
        # Protected semantics must never be inferred from substring overlap
        # (for example ``move`` is a substring of ``move_commitment``). Any
        # non-exact rename must be explicit in a typed, schema-checked plan.
        return field if field in props else None
