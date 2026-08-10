"""Shared builders for tool schemas, introspection results, and native plans."""

from __future__ import annotations

from cop_worker.protocol.introspector import IntrospectionResult, ToolSchema
from cop_worker.protocol.mapping_plan import (
    ProtocolMappingPlan,
)


def _tool(
    name: str, description: str, props: dict, required: list[str] | None = None
) -> ToolSchema:
    props = {
        **props,
        "gamelet": props.get("gamelet", "integer"),
        "reason": props.get("reason", "string"),
        "result_hash": props.get("result_hash", "string"),
        "signed_agreement": props.get("signed_agreement", "object"),
        "signed_audit_summary": props.get("signed_audit_summary", "object"),
        "signature": props.get("signature", "string"),
    }
    return ToolSchema(
        name=name,
        description=description,
        input_schema={
            "type": "object",
            "properties": {k: {"type": v} for k, v in props.items()},
            "required": required or ["game_id", "role"],
        },
    )


def _intro(server: str, tools: list[ToolSchema], schema_digest: str = "") -> IntrospectionResult:
    import hashlib

    digest = (
        schema_digest or hashlib.sha256("|".join(t.name for t in tools).encode()).hexdigest()[:16]
    )
    return IntrospectionResult(
        server_name=server,
        server_version="1.0",
        protocol_version="2024-11-05",
        tools=tools,
        resources=[],
        prompts=[],
        raw_capabilities={"tools": {}},
        schema_digest=digest,
    )


def _native_plan(tool_name: str = "action", server: str = "native") -> ProtocolMappingPlan:
    return ProtocolMappingPlan.native_plan(tool_name, server)
