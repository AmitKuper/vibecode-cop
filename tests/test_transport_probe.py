"""Fast unit tests for TransportProbe (both package copies).

The real HTTP/SSE connectors are monkeypatched, so probe() runs offline with no
sockets and no timeouts. stdio probing needs no network at all.
"""

from __future__ import annotations

import pytest

from cop_worker.protocol import transport_probe as cop_tp
from league_manager.protocol import transport_probe as lm_tp

MODS = [cop_tp, lm_tp]


def _result(mod, transport):
    return mod.ProbeResult(
        transport=transport, base_url="http://x", mcp_endpoint="http://x/mcp", latency_ms=1.0
    )


@pytest.mark.parametrize("mod", MODS)
async def test_probe_stdio_needs_no_network(mod):
    result = await mod.TransportProbe().probe('stdio://run "my server" --port 1')
    assert result.transport == mod.TransportType.STDIO
    assert result.stdio_command[0] == "run" and "my server" in result.stdio_command


@pytest.mark.parametrize("mod", MODS)
async def test_probe_prefers_streamable_http(mod, monkeypatch):
    async def ok(base, timeout):
        return _result(mod, mod.TransportType.STREAMABLE_HTTP)

    monkeypatch.setattr(mod, "_try_streamable_http", ok)
    result = await mod.TransportProbe().probe("http://peer")
    assert result.transport == mod.TransportType.STREAMABLE_HTTP


@pytest.mark.parametrize("mod", MODS)
async def test_probe_falls_back_to_sse(mod, monkeypatch):
    async def none(base, timeout):
        return None

    async def sse(base, timeout):
        return _result(mod, mod.TransportType.SSE)

    monkeypatch.setattr(mod, "_try_streamable_http", none)
    monkeypatch.setattr(mod, "_try_sse", sse)
    result = await mod.TransportProbe().probe("http://peer")
    assert result.transport == mod.TransportType.SSE


@pytest.mark.parametrize("mod", MODS)
async def test_probe_returns_unknown_when_nothing_responds(mod, monkeypatch):
    async def none(base, timeout):
        return None

    monkeypatch.setattr(mod, "_try_streamable_http", none)
    monkeypatch.setattr(mod, "_try_sse", none)
    result = await mod.TransportProbe().probe("http://peer")
    assert result.transport == mod.TransportType.UNKNOWN


@pytest.mark.parametrize("mod", MODS)
def test_probe_sync_wraps_async(mod):
    result = mod.TransportProbe().probe_sync("stdio://server")
    assert result.transport == mod.TransportType.STDIO
