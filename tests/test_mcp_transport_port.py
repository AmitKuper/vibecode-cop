"""Tests for TransportPort / GameProtocolPort abstractions (Phase 10A/10B)."""

import inspect

import pytest

from agent.mcp.protocol_port import GameProtocolPort, ProtocolMapping
from agent.mcp.transport_port import SSETransportAdapter, StubTransportAdapter

# ---------------------------------------------------------------------------
# StubTransportAdapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stub_transport_sends_to_handler():
    async def handler(tool_name: str, params: dict) -> dict:
        return {"echoed": tool_name, "params": params}

    stub = StubTransportAdapter(handler)
    await stub.connect("unused")
    result = await stub.send("ping", {"x": 1})
    assert result["echoed"] == "ping"
    assert result["params"] == {"x": 1}


@pytest.mark.asyncio
async def test_stub_transport_requires_connect():
    async def handler(tool_name: str, params: dict) -> dict:
        return {}

    stub = StubTransportAdapter(handler)
    with pytest.raises(RuntimeError, match="Not connected"):
        await stub.send("ping", {})


def test_sse_transport_type():
    sse = SSETransportAdapter()
    assert sse.transport_type == "SSE"


# ---------------------------------------------------------------------------
# ProtocolMapping
# ---------------------------------------------------------------------------


def test_protocol_mapping_locks():
    mapping = ProtocolMapping.default()
    assert not mapping.is_locked
    h = mapping.lock()
    assert mapping.is_locked
    assert isinstance(h, str) and len(h) == 64  # sha256 hex


def test_protocol_mapping_unlocked_raises():
    mapping = ProtocolMapping.default()
    with pytest.raises(RuntimeError, match="Step-0 incomplete"):
        mapping.tool_for("commit")


def test_protocol_mapping_unknown_phase():
    mapping = ProtocolMapping.default()
    mapping.lock()
    with pytest.raises(KeyError, match="nonexistent"):
        mapping.tool_for("nonexistent")


# ---------------------------------------------------------------------------
# GameProtocolPort dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_protocol_port_dispatches_commit():
    calls: list[tuple] = []

    async def handler(tool_name: str, params: dict) -> dict:
        calls.append((tool_name, params))
        return {"status": "ok"}

    stub = StubTransportAdapter(handler)
    await stub.connect("x")
    mapping = ProtocolMapping.default()
    mapping.lock()
    port = GameProtocolPort(stub, mapping)
    await port.commit({"h_commit": "abc"})
    assert calls[0][0] == "action"
    assert calls[0][1]["phase"] == "commit"
    assert calls[0][1]["h_commit"] == "abc"


@pytest.mark.asyncio
async def test_protocol_port_dispatches_reveal():
    calls: list[tuple] = []

    async def handler(tool_name: str, params: dict) -> dict:
        calls.append((tool_name, params))
        return {"status": "ok"}

    stub = StubTransportAdapter(handler)
    await stub.connect("x")
    mapping = ProtocolMapping.default()
    mapping.lock()
    port = GameProtocolPort(stub, mapping)
    await port.reveal({"move": "N", "nonce": "xyz"})
    assert calls[0][0] == "action"
    assert calls[0][1]["phase"] == "reveal"
    assert calls[0][1]["move"] == "N"


# ---------------------------------------------------------------------------
# No LLM import in crypto path
# ---------------------------------------------------------------------------


def test_no_llm_in_crypto_path():
    """GameProtocolPort must not import any LLM library."""
    import agent.mcp.protocol_port as pp_mod

    source = inspect.getsource(pp_mod)
    # Check for import statements containing LLM library names (not comments/docstrings)
    import_lines = [
        line
        for line in source.splitlines()
        if line.strip().startswith("import") or line.strip().startswith("from")
    ]
    llm_import_markers = ["openai", "anthropic", "litellm", "langchain", "crewai"]
    for marker in llm_import_markers:
        matching = [ln for ln in import_lines if marker in ln.lower()]
        assert not matching, f"protocol_port.py imports LLM library {marker!r}: {matching}"
