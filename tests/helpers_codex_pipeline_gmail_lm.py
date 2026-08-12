"""Shared negotiation fixtures for the codex pipeline Gmail contract LM tests."""

from __future__ import annotations

import json

from league_manager.protocol.introspector import IntrospectionResult, ToolSchema
from league_manager.protocol.transport_probe import ProbeResult, TransportType


def _probe(transport=TransportType.STREAMABLE_HTTP):
    return ProbeResult(transport, "http://peer", "http://peer/mcp", 1.0, "notes")


def _intro(digest="native"):
    action = ToolSchema(
        "action",
        "safe",
        {"properties": {"game_id": {}, "message_json": {}, "signature": {}}},
    )
    start = ToolSchema("start_game", "safe", {"properties": {"message_json": {}, "signature": {}}})
    conformance = ToolSchema(
        "protocol_conformance",
        "side-effect-free conformance",
        {
            "properties": {
                "phase": {},
                "game_id": {},
                "request_digest": {},
                "idempotency_key": {},
            }
        },
    )
    return IntrospectionResult("peer", "1", "p", [action, start, conformance], [], [], {}, digest)


async def _conforming_probe(tool_name, params):
    if tool_name == "protocol_conformance":
        return {
            "ok": True,
            "game_id": params["game_id"],
            "phase": params["phase"],
            "idempotent": True,
            "side_effects": 0,
            "canonical_order": True,
            "canonical_json_bytes": True,
            "commitment_binding": True,
            "nonce_final_audit_only": True,
            "comprehensive_audit": True,
            "result_agreement": True,
        }
    body = json.loads(params["message_json"])
    return {
        "ok": False,
        "error": "invalid probe signature",
        "game_id": params.get("game_id", body["game_id"]),
        "phase": body["phase"],
    }


async def _patch_transport(monkeypatch, probe=None, intro=None):
    chosen_probe = probe or _probe()
    chosen_intro = intro or _intro()

    async def fake_probe(_self, _url):
        return chosen_probe

    async def fake_intro(_self, _probe_result):
        return chosen_intro

    monkeypatch.setattr("league_manager.protocol.pipeline.TransportProbe.probe", fake_probe)
    monkeypatch.setattr("league_manager.protocol.pipeline.MCPIntrospector.introspect", fake_intro)

    monkeypatch.setattr(
        "league_manager.protocol.pipeline._discovered_tool_caller", lambda _probe: _conforming_probe
    )
