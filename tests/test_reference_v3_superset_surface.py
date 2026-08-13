"""Pin superset tolerance in the reference-v3 surface recognizer.

Live finding (najamjad, 2026-08-13): a peer may advertise BOTH ``message`` and
``payload`` on every tool with neither required — a superset that accepts every
kit-shaped call unchanged. Discovery must accept it, while still refusing a
surface whose expected argument is missing or non-object.
"""

from __future__ import annotations

from cop_worker.protocol.introspector import IntrospectionResult, ToolSchema
from cop_worker.protocol.reference_v3 import REFERENCE_V3_TOOLS, is_reference_v3_surface


def _intro(schema_for: dict) -> IntrospectionResult:
    tools = [
        ToolSchema(name=name, description=f"reference-v3 {name}", input_schema=schema)
        for name, schema in schema_for.items()
    ]
    return IntrospectionResult(
        server_name="najamjad-like",
        server_version="1",
        protocol_version="1",
        tools=tools,
        resources=[],
        prompts=[],
        raw_capabilities={},
        schema_digest="d1",
    )


def _alias_schema() -> dict:
    return {
        "type": "object",
        "properties": {"message": {"type": "object"}, "payload": {"type": "object"}},
        "required": [],
    }


def test_alias_superset_surface_is_accepted():
    intro = _intro({name: _alias_schema() for name in REFERENCE_V3_TOOLS})
    assert is_reference_v3_surface(intro)


def test_exact_kit_surface_still_accepted():
    intro = _intro(
        {
            name: {
                "type": "object",
                "properties": {arg: {"type": "object"}},
                "required": [arg],
            }
            for name, arg in REFERENCE_V3_TOOLS.items()
        }
    )
    assert is_reference_v3_surface(intro)


def test_missing_expected_argument_still_refused():
    schemas = {name: _alias_schema() for name in REFERENCE_V3_TOOLS}
    # submit_audit advertises only "message" — the payload asymmetry is absent.
    schemas["submit_audit"] = {
        "type": "object",
        "properties": {"message": {"type": "object"}},
        "required": [],
    }
    assert not is_reference_v3_surface(_intro(schemas))


def test_non_object_expected_argument_still_refused():
    schemas = {name: _alias_schema() for name in REFERENCE_V3_TOOLS}
    schemas["negotiate"] = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": [],
    }
    assert not is_reference_v3_surface(_intro(schemas))


def test_untyped_expected_argument_tolerated():
    # Some frameworks omit "type" on dict-typed params; absence is not refusal.
    schemas = {name: _alias_schema() for name in REFERENCE_V3_TOOLS}
    schemas["receive_turn"] = {"type": "object", "properties": {"message": {}}, "required": []}
    assert is_reference_v3_surface(_intro(schemas))
