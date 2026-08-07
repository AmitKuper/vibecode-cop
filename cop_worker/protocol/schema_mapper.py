"""Deterministic schema-to-protocol mapper used before any LLM fallback."""

from __future__ import annotations

from cop_worker.protocol.introspector import IntrospectionResult, ToolSchema
from cop_worker.protocol.mapping_plan import (
    CompatibilityVerdict,
    FieldMapping,
    PhaseMapping,
    ProtocolMappingPlan,
)

_FIELDS = {
    "game_id": ("game_id", "game_uid", "match_id", "session_id"),
    "gamelet": ("gamelet", "game_number", "round"),
    "step": ("step", "step_num", "turn", "turn_number", "sequence"),
    "role": ("role", "player_role", "actor", "side"),
    "phase": ("phase", "action_phase", "message_type", "kind"),
    "config_sha256": ("config_sha256", "config_hash", "configuration_hash"),
    "timestamp": ("timestamp", "ts", "sent_at"),
    "signature": ("signature", "sig", "message_signature"),
    "commitment": ("commitment", "h_commit", "move_commitment", "commit_hash"),
    "hint": ("hint", "message", "utterance", "text"),
    "move": ("move", "action", "direction"),
    "nonces": ("nonces", "audit_nonces", "nonce_map"),
    "reason": ("reason", "outcome", "winner"),
    "result_hash": ("result_hash", "agreement_hash"),
    "signed_agreement": ("signed_agreement", "result_agreement", "agreement"),
    "signed_audit_summary": ("signed_audit_summary", "audit_summary", "signed_summary"),
}
_PHASE_TERMS = {
    "start_game": ("start_game", "start", "begin", "handshake"),
    "commit": ("commit_move", "commit", "lock", "seal"),
    "reveal": ("reveal_move", "reveal", "open_move"),
    "final_audit": ("final_audit", "audit", "verify_nonce"),
    "audit_summary": ("audit_summary", "signed_audit", "summary"),
    "game_end": ("game_end", "finish", "outcome"),
    "result_agreement": ("result_agreement", "agreement", "final_result", "result"),
    "abort": ("abort", "technical_loss", "cancel"),
}
_BASE = ("game_id", "step", "role", "phase", "config_sha256", "timestamp", "signature")
_EXTRAS = {
    "start_game": ("gamelet",),
    "commit": ("commitment", "hint"),
    "reveal": ("move",),
    "final_audit": ("nonces",),
    "audit_summary": ("signed_audit_summary",),
    "game_end": ("reason",),
    "result_agreement": ("result_hash", "signed_agreement"),
    "abort": ("reason",),
}


def infer_mapping_plan(intro: IntrospectionResult) -> ProtocolMappingPlan:
    """Infer split tools, renames, nesting, packing, enums, and responses."""
    mappings: list[PhaseMapping] = []
    gaps: list[str] = []
    for phase in sorted(ProtocolMappingPlan.REQUIRED_PHASES):
        tool = _select_tool(intro.tools, phase)
        if tool is None:
            gaps.append(f"no remote tool for {phase}")
            continue
        fields = _map_fields(tool, phase)
        mapped = {item.canonical_field for item in fields}
        required = _required_fields(phase)
        if not _is_packed(fields):
            missing = required - mapped
            gaps.extend(f"{phase} cannot transport {name}" for name in sorted(missing))
        mappings.append(
            PhaseMapping(
                phase=phase,
                remote_tool=tool.name,
                field_mappings=fields,
                response_extraction=_responses(tool),
                notes="deterministic schema discovery",
                multiphase_envelope=(
                    any(item.canonical_field == "phase" for item in fields) or _is_packed(fields)
                ),
            )
        )
    verdict = CompatibilityVerdict.INCOMPATIBLE if gaps else CompatibilityVerdict.COMPATIBLE
    primary = next((item.remote_tool for item in mappings if item.phase == "commit"), "")
    conformance = next(
        (
            tool.name
            for tool in intro.tools
            if "conformance" in f"{tool.name} {tool.description}".lower()
        ),
        "",
    )
    return ProtocolMappingPlan(
        remote_tool_name=primary,
        remote_server_name=intro.server_name,
        remote_schema_digest=intro.schema_digest,
        phase_mappings=mappings,
        capability_gaps=gaps,
        verdict=verdict,
        confidence=0.92 if not gaps else 0.35,
        agent_model="deterministic-schema-agent",
        agent_version="2.0",
        conformance_tool=conformance,
    )


def _select_tool(tools: list[ToolSchema], phase: str) -> ToolSchema | None:
    if not tools:
        return None
    terms = _PHASE_TERMS[phase]
    scored = []
    for tool in tools:
        haystack = f"{tool.name} {tool.description}".lower()
        score = max((100 - i * 5 for i, term in enumerate(terms) if term in haystack), default=0)
        if "action" in tool.name.lower() or tool.name.lower() == "game_move":
            score = max(score, 20)
        scored.append((score, tool.name, tool))
    score, _name, selected = max(scored, key=lambda item: (item[0], item[1]))
    return selected if score else None


def _map_fields(tool: ToolSchema, phase: str) -> list[FieldMapping]:
    props = tool.input_schema.get("properties", {})
    if "packed_message" in props:
        return [
            FieldMapping("game_id", "game_id"),
            FieldMapping("message_json", "packed_message"),
            FieldMapping("signature", "signature"),
        ]
    fields = []
    for canonical in (*_BASE, *_EXTRAS[phase]):
        remote = _destination(canonical, props)
        if remote is None:
            continue
        transform = "identity"
        args = {}
        if canonical == "move" and _uses_long_moves(tool, props.get(remote, {})):
            transform = "enum_map"
            args = {
                "mapping": {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST", "STAY": "STAY"}
            }
        fields.append(
            FieldMapping(
                canonical,
                remote,
                transform=transform,
                transform_args=args,
                required=canonical in _required_fields(phase),
            )
        )
    mapped_roots = {item.remote_field.split(".")[0] for item in fields}
    for name in tool.input_schema.get("required", []):
        schema = props.get(name, {})
        if name not in mapped_roots and ("const" in schema or "default" in schema):
            fields.append(
                FieldMapping(
                    "__constant__", name, constant_value=schema.get("const", schema.get("default"))
                )
            )
    return fields


def _destination(canonical: str, props: dict) -> str | None:
    aliases = _FIELDS[canonical]
    for alias in aliases:
        if alias in props:
            return alias
    for root, schema in props.items():
        nested = schema.get("properties", {}) if isinstance(schema, dict) else {}
        for alias in aliases:
            if alias in nested:
                return f"{root}.{alias}"
    if {"header", "body"}.issubset(props):
        root = "header" if canonical in _BASE or canonical == "gamelet" else "body"
        return f"{root}.{aliases[0]}"
    return None


def _required_fields(phase: str) -> set[str]:
    common = {"game_id", "role", "signature"}
    return (
        common
        | {
            "start_game": {"gamelet"},
            "commit": {"step", "commitment"},
            "reveal": {"step", "move"},
            "final_audit": {"nonces"},
            "audit_summary": {"signed_audit_summary"},
            "game_end": {"reason"},
            "result_agreement": {"signed_agreement"},
            "abort": {"reason"},
        }[phase]
    )


def _is_packed(fields: list[FieldMapping]) -> bool:
    return {item.canonical_field for item in fields}.issuperset({"message_json", "signature"})


def _uses_long_moves(tool: ToolSchema, schema: dict) -> bool:
    values: set[str] = set()

    def collect(value) -> None:
        if isinstance(value, dict):
            values.update(str(item) for item in value.get("enum", []))
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)

    collect(schema)
    return "long move" in tool.description.lower() or "NORTH" in values


def _responses(tool: ToolSchema) -> dict[str, str]:
    props = tool.output_schema.get("properties", {})
    if "data" in props or "nested response" in tool.description.lower():
        return {
            "ok": "data.ok",
            "phase": "data.phase",
            "game_id": "data.game_id",
            "winner": "data.winner",
        }
    return {"ok": "ok", "phase": "phase", "winner": "winner", "game_id": "game_id"}
