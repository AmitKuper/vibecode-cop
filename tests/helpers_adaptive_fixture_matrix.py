"""Shared fixture-server helpers for the real-process adaptive MCP matrix tests."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from fastmcp.client.transports import SSETransport, StdioTransport, StreamableHttpTransport

from cop_worker.protocol.transport_probe import ProbeResult, TransportProbe, TransportType

SERVER = Path(__file__).parent / "fixtures" / "adaptive_peer_server.py"


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
