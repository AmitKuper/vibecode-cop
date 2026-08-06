"""Real-process adaptive MCP matrix required by the v11 contract."""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.client.transports import SSETransport, StdioTransport, StreamableHttpTransport

from agent.adaptive.adapter import DeterministicProtocolAdapter
from agent.adaptive.conformance import ConformanceProbes
from agent.adaptive.introspector import MCPIntrospector
from agent.adaptive.profile import ProtocolProfile
from agent.adaptive.protocol_agent import ProtocolUnderstandingAgent
from agent.adaptive.transport_probe import ProbeResult, TransportProbe, TransportType
from agent.adaptive.verifier import StaticSemanticVerifier

SERVER = Path(__file__).parent / "fixtures" / "adaptive_peer_server.py"
COMPATIBLE = (
    ("native", "stdio"),
    ("split", "stdio"),
    ("renamed", "stdio"),
    ("nested", "stdio"),
    ("packed", "stdio"),
    ("enum_aliases", "stdio"),
    ("optional_extra", "stdio"),
    ("nested_response", "stdio"),
    ("streamable_http", "http"),
    ("sse", "sse"),
)
INCOMPATIBLE = (
    "nonce_in_reveal",
    "missing_commitment",
    "missing_final_result",
    "mutable_canonicalization",
    "phase_order",
    "no_idempotency",
    "prompt_injection",
    "protected_corruption",
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def _http_server(variant: str, transport: str):
    port = _free_port()
    command = [
        sys.executable,
        str(SERVER),
        "--variant",
        variant,
        "--transport",
        transport,
        "--port",
        str(port),
    ]
    process = subprocess.Popen(  # noqa: S603 - fixed local acceptance fixture
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 15
        probe = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("fixture server exited early")
            probe = TransportProbe(timeout_s=0.5).probe_sync(url)
            if probe.transport != TransportType.UNKNOWN:
                break
            time.sleep(0.05)
        if probe is None or probe.transport == TransportType.UNKNOWN:
            raise RuntimeError(f"fixture server did not become ready at {url}")
        yield probe
    finally:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@contextmanager
def _fixture_probe(variant: str, transport: str):
    if transport == "stdio":
        command = (
            sys.executable,
            str(SERVER),
            "--variant",
            variant,
            "--transport",
            "stdio",
        )
        yield ProbeResult(
            TransportType.STDIO,
            "stdio",
            "stdio",
            0.0,
            f"actual {variant} stdio fixture",
            command,
        )
    else:
        with _http_server(variant, transport) as probe:
            yield probe


def _transport(probe: ProbeResult):
    if probe.transport == TransportType.STDIO:
        return StdioTransport(probe.stdio_command[0], list(probe.stdio_command[1:]))
    if probe.transport == TransportType.SSE:
        return SSETransport(probe.mcp_endpoint)
    return StreamableHttpTransport(probe.mcp_endpoint)


def _result_dict(result) -> dict:
    if isinstance(getattr(result, "data", None), dict):
        return result.data
    if isinstance(getattr(result, "structured_content", None), dict):
        return result.structured_content
    if not result.content:
        return {"ok": not result.is_error}
    value = result.content[0].text
    parsed = json.loads(value)
    assert isinstance(parsed, dict)
    return parsed


def _canonical(phase: str, gamelet: int, *, game_id: str | None = None) -> dict:
    value = {
        "game_id": game_id or f"FIXTURE_GAME_{gamelet}",
        "gamelet": gamelet,
        "step": 1,
        "role": "cop",
        "phase": phase,
        "config_sha256": "c" * 64,
        "timestamp": "2026-08-06T00:00:00Z",
        "signature": "fixture-valid",
        "commitment": "d" * 64,
        "hint": "A bounded fixture message.",
        "move": "N",
        "nonces": {"1": "fixture-nonce"},
        "signed_audit_summary": {"signature": "fixture-valid"},
        "result_hash": "e" * 64,
        "signed_agreement": {"signature": "fixture-valid"},
        "reason": "fixture-complete",
    }
    value["message_json"] = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return value


async def _exercise_compatible(probe: ProbeResult) -> tuple[int, ProtocolProfile]:
    intro = await MCPIntrospector(timeout_s=15).introspect(probe)
    plan = ProtocolUnderstandingAgent().create_plan(intro)
    verification = StaticSemanticVerifier().verify(plan)
    assert verification.passed, verification.errors
    adapter = DeterministicProtocolAdapter(plan)
    profile = ProtocolProfile.build(probe, plan)
    assert profile.verify_integrity(intro.schema_digest)

    accepted = 0
    async with Client(_transport(probe)) as client:

        async def call(tool_name: str, params: dict) -> dict:
            return _result_dict(await client.call_tool(tool_name, params))

        conformance = await ConformanceProbes(adapter, plan).run_remote(call)
        assert conformance.all_passed, conformance.failed_probes()
        for gamelet in range(1, 7):
            for phase in (
                "start_game",
                "commit",
                "reveal",
                "final_audit",
                "audit_summary",
                "game_end",
            ):
                canonical = _canonical(phase, gamelet)
                request = adapter.adapt_request(phase, canonical)
                response = await call(request.tool_name, request.params)
                adapted = adapter.adapt_response(
                    phase, response, {"game_id": canonical["game_id"], "phase": phase}
                )
                assert adapted.extracted["ok"] is True
                accepted += 1
        canonical = _canonical("result_agreement", 6, game_id="FIXTURE_SERIES")
        request = adapter.adapt_request("result_agreement", canonical)
        response = await call(request.tool_name, request.params)
        adapted = adapter.adapt_response(
            "result_agreement",
            response,
            {"game_id": "FIXTURE_SERIES", "phase": "result_agreement"},
        )
        assert adapted.extracted["ok"] is True
        accepted += 1

    assert adapter.per_turn_llm_calls == 0
    return accepted, profile


@pytest.mark.parametrize(("variant", "transport"), COMPATIBLE)
def test_actual_compatible_mcp_process_completes_six_gamelets(variant: str, transport: str) -> None:
    with _fixture_probe(variant, transport) as probe:
        accepted, profile = asyncio.run(_exercise_compatible(probe))
    assert accepted == 37
    assert profile.remote_transport in {"stdio", "streamable_http", "sse"}


@pytest.mark.parametrize("variant", INCOMPATIBLE)
def test_actual_incompatible_mcp_process_rejected_before_commit(variant: str) -> None:
    async def verify_rejected(probe: ProbeResult) -> None:
        try:
            intro = await MCPIntrospector(timeout_s=15).introspect(probe)
        except ValueError as exc:
            assert variant == "prompt_injection"
            assert "Prompt injection" in str(exc)
            return
        plan = ProtocolUnderstandingAgent().create_plan(intro)
        verification = StaticSemanticVerifier().verify(plan)
        if not verification.passed:
            return
        adapter = DeterministicProtocolAdapter(plan)
        async with Client(_transport(probe)) as client:

            async def call(tool_name: str, params: dict) -> dict:
                return _result_dict(await client.call_tool(tool_name, params))

            report = await ConformanceProbes(adapter, plan).run_remote(call)
        assert not report.all_passed, "incompatible peer reached first counted commitment"

    with _fixture_probe(variant, "stdio") as probe:
        asyncio.run(verify_rejected(probe))
