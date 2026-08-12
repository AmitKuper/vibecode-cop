"""Reference-v3 message construction and both client/server directions."""

from __future__ import annotations

import sys
from pathlib import Path


def _messages() -> tuple[dict, dict, dict, dict]:
    from agent.adaptive.reference_v3 import build_negotiation, build_turn, default_terms

    greeting = build_negotiation(
        terms=default_terms(),
        nonce="ab" * 16,
        group_id="sparring-vibecode-interop",
        group_name="Vibecode interoperability verifier",
        role="police",
        sub_game_number=1,
    )
    payload = {
        "step": 1,
        "role": "police",
        "sub_game": 1,
        "state": "grid=7x7;self=[0, 0];barriers=[]",
        "position": [0, 0],
        "move": "STAY",
        "intent": "truth",
        "hint": "I am testing interoperability",
        "verdict": "moved",
    }
    turn, record = build_turn(
        record_payload=payload,
        nonce="cd" * 16,
        sender="police",
        hint=payload["hint"],
        smell_grid={"0,0": 0.8},
    )
    audit = {"sender": "police", "records": [record], "result_claim": "timeout"}
    control = {
        "kind": "status",
        "sender": "police",
        "sub_game_number": 1,
        "status": "interop_probe",
        "step_budget": 30.0,
        "payload": {"side_effect_free": True},
    }
    return greeting, turn, audit, control


async def _our_client_to_external(url: str) -> dict:
    from agent.adaptive.pipeline import discover_reference_v3

    profile, session = await discover_reference_v3(url)
    greeting, turn, audit, control = _messages()
    responses = [
        await session.send_negotiation(greeting),
        await session.send_turn(turn, audit["records"][0]),
        await session.send_audit("police", "timeout"),
        await session.send_control(control),
    ]
    if not all(response.get("ok") for response in responses):
        raise RuntimeError(f"external server rejected a reference-v3 call: {responses}")
    return {
        "profile_hash": profile.profile_hash,
        "schema_digest": profile.schema_digest,
        "calls": 4,
        "per_turn_llm_calls": session.per_turn_llm_calls,
    }


def _external_client_to_ours(kit: Path, url: str) -> dict:
    sys.path.insert(0, str(kit))
    try:
        from sparring.transport.client import McpClient

        client = McpClient(url, timeout=10.0)
        greeting, turn, audit, control = _messages()
        try:
            responses = [
                client.negotiate(greeting),
                client.receive_turn(turn),
                client.submit_audit(audit),
                client.receive_control(control),
            ]
        finally:
            client.close()
    finally:
        sys.path.remove(str(kit))
    if not all(response.get("ok") for response in responses):
        raise RuntimeError(f"external client rejected our MCP surface: {responses}")
    return {"calls": 4, "argument_asymmetry": "submit_audit(payload)"}


def _serve_local(host: str, port: int) -> int:
    from agent.adaptive.reference_v3 import ReferenceV3Session, register_reference_v3_tools
    from fastmcp import FastMCP

    async def unavailable(_tool: str, _params: dict) -> dict:
        raise RuntimeError("outbound transport is not configured in the verifier server")

    app = FastMCP(name="vibecode-reference-v3-interop")
    register_reference_v3_tools(app, ReferenceV3Session(unavailable))
    app.run(transport="http", host=host, port=port, show_banner=False)
    return 0
