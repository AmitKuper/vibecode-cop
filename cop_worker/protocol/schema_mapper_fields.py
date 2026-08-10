"""Field mapping internals for the static schema mapper."""

from __future__ import annotations

from cop_worker.protocol.introspector import ToolSchema
from cop_worker.protocol.mapping_plan import (
    FieldMapping,
)
from cop_worker.protocol.schema_mapper import (  # noqa: PLC0415
    _BASE,
    _EXTRAS,
    _FIELDS,
)


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
