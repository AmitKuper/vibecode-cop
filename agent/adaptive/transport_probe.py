"""TransportProbe: discover which MCP transport an opponent server supports.

Probes Streamable HTTP, legacy SSE, and stdio in that order, with bounded
deadlines and no game mutation.
"""

from __future__ import annotations

import asyncio
import enum
import json
import logging
from contextlib import suppress
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx

logger = logging.getLogger(__name__)

PROBE_TIMEOUT_S = 5.0


def normalize_mcp_base_url(endpoint: str) -> str:
    """Return the server base without corrupting host/path characters.

    ``str.rstrip('/mcp')`` removes a *set of characters*, so a URL such as
    ``https://team.com/mcp`` becomes ``https://team.co``.  Only an exact MCP
    transport suffix is removed here; arbitrary custom paths are preserved.
    """
    value = endpoint.strip().rstrip("/")
    if value.startswith("stdio://"):
        return value
    parsed = urlsplit(value)
    path = parsed.path
    for suffix in ("/mcp", "/sse"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment)).rstrip(
        "/"
    )


class TransportType(enum.StrEnum):
    STREAMABLE_HTTP = "streamable_http"
    SSE = "sse"
    STDIO = "stdio"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProbeResult:
    transport: TransportType
    base_url: str
    mcp_endpoint: str
    latency_ms: float
    probe_notes: str = ""
    stdio_command: tuple[str, ...] = ()


async def _try_streamable_http(base_url: str, timeout: float) -> ProbeResult | None:
    """POST /mcp with MCP initialize message — Streamable HTTP style."""
    endpoint = base_url.rstrip("/") + "/mcp"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "probe", "version": "1.0"},
        },
    }
    try:
        import time

        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(
                endpoint,
                json=payload,
                headers={"Accept": "application/json, text/event-stream"},
            )
        latency_ms = (time.monotonic() - t0) * 1000
        content_type = r.headers.get("content-type", "")
        bodies: list[dict] = []
        if "application/json" in content_type:
            with suppress(ValueError, TypeError):
                bodies.append(r.json())
        elif "event-stream" in content_type:
            for line in r.text.splitlines():
                if line.startswith("data:"):
                    with suppress(ValueError, TypeError):
                        bodies.append(json.loads(line.removeprefix("data:").strip()))
        valid_initialize = any(
            isinstance(body, dict)
            and body.get("jsonrpc") == "2.0"
            and isinstance(body.get("result"), dict)
            and ("protocolVersion" in body["result"] or "serverInfo" in body["result"])
            for body in bodies
        )
        if r.status_code == 200 and valid_initialize:
            return ProbeResult(
                transport=TransportType.STREAMABLE_HTTP,
                base_url=base_url,
                mcp_endpoint=endpoint,
                latency_ms=latency_ms,
                probe_notes=f"HTTP {r.status_code}",
            )
    except Exception as exc:
        logger.debug("Streamable HTTP probe failed for %s: %s", base_url, exc)
    return None


async def _try_sse(base_url: str, timeout: float) -> ProbeResult | None:
    """GET /sse — legacy SSE transport handshake."""
    endpoint = base_url.rstrip("/") + "/sse"
    try:
        import time

        t0 = time.monotonic()
        async with (
            httpx.AsyncClient(timeout=timeout) as c,
            # An SSE response is intentionally unbounded. Inspect the handshake
            # headers without asking httpx to consume the response body.
            c.stream(
                "GET",
                endpoint,
                headers={"Accept": "text/event-stream"},
                follow_redirects=True,
            ) as r,
        ):
            latency_ms = (time.monotonic() - t0) * 1000
            content_type = r.headers.get("content-type", "")
            if r.status_code == 200 and "event-stream" in content_type:
                return ProbeResult(
                    transport=TransportType.SSE,
                    base_url=base_url,
                    mcp_endpoint=endpoint,
                    latency_ms=latency_ms,
                    probe_notes="SSE event-stream confirmed",
                )
    except Exception as exc:
        logger.debug("SSE probe failed for %s: %s", base_url, exc)
    return None


class TransportProbe:
    """Discovers the MCP transport an opponent server speaks.

    Tries Streamable HTTP first (preferred), then legacy SSE, then signals
    UNKNOWN. Does not mutate game state.
    """

    def __init__(self, timeout_s: float = PROBE_TIMEOUT_S) -> None:
        self._timeout = timeout_s

    async def probe(self, base_url: str) -> ProbeResult:
        """Return the first working transport, or UNKNOWN."""
        if base_url.startswith("stdio://"):
            return self.stdio_result(base_url.removeprefix("stdio://"))
        result = await _try_streamable_http(base_url, self._timeout)
        if result:
            logger.info("TransportProbe: Streamable HTTP confirmed at %s", result.mcp_endpoint)
            return result

        result = await _try_sse(base_url, self._timeout)
        if result:
            logger.info("TransportProbe: SSE confirmed at %s", result.mcp_endpoint)
            return result

        logger.warning("TransportProbe: no known transport at %s", base_url)
        return ProbeResult(
            transport=TransportType.UNKNOWN,
            base_url=base_url,
            mcp_endpoint=base_url,
            latency_ms=0.0,
            probe_notes="no transport responded within deadline",
        )

    def probe_sync(self, base_url: str) -> ProbeResult:
        return asyncio.run(self.probe(base_url))

    @staticmethod
    def stdio_result(local_command: str = "") -> ProbeResult:
        import os
        import shlex

        parts = shlex.split(local_command, posix=os.name != "nt")
        command = tuple(
            part[1:-1] if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'" else part
            for part in parts
        )
        return ProbeResult(
            transport=TransportType.STDIO,
            base_url="stdio",
            mcp_endpoint="stdio",
            latency_ms=0.0,
            probe_notes=f"local stdio fixture: {local_command}",
            stdio_command=command,
        )
