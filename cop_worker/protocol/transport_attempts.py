"""Transport attempt coroutines: streamable HTTP and SSE."""

from __future__ import annotations

import json
import logging
from contextlib import suppress

import httpx

from cop_worker.protocol.transport_types import ProbeResult, TransportType

logger = logging.getLogger(__name__)

PROBE_TIMEOUT_S = 5.0


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
        bodies: list[dict] = []
        status_code = 0
        async with (
            httpx.AsyncClient(timeout=timeout) as c,
            c.stream(
                "POST",
                endpoint,
                json=payload,
                headers={"Accept": "application/json, text/event-stream"},
            ) as r,
        ):
            status_code = r.status_code
            content_type = r.headers.get("content-type", "")
            # Read only the first chunk (avoid blocking on persistent SSE connections)
            raw_lines: list[str] = []
            async for line in r.aiter_lines():
                raw_lines.append(line)
                if line.startswith("data:"):
                    with suppress(ValueError, TypeError):
                        bodies.append(json.loads(line.removeprefix("data:").strip()))
                    break  # got first data line — enough for detection
                if len(raw_lines) > 20:
                    break
            if not bodies and "application/json" in content_type:
                text = "\n".join(raw_lines)
                with suppress(ValueError, TypeError):
                    bodies.append(json.loads(text))
        latency_ms = (time.monotonic() - t0) * 1000
        valid_initialize = any(
            isinstance(body, dict)
            and body.get("jsonrpc") == "2.0"
            and isinstance(body.get("result"), dict)
            and ("protocolVersion" in body["result"] or "serverInfo" in body["result"])
            for body in bodies
        )
        if status_code == 200 and valid_initialize:
            return ProbeResult(
                transport=TransportType.STREAMABLE_HTTP,
                base_url=base_url,
                mcp_endpoint=endpoint,
                latency_ms=latency_ms,
                probe_notes=f"HTTP {status_code}",
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
