"""Transport probe result types and URL normalization."""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

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
