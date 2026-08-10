"""TransportProbe: discover which MCP transport an opponent server supports.

Probes Streamable HTTP, legacy SSE, and stdio in that order, with bounded
deadlines and no game mutation.
"""

from __future__ import annotations

import asyncio
import logging

from cop_worker.protocol.transport_attempts import (  # noqa: F401
    _try_sse,
    _try_streamable_http,
)
from cop_worker.protocol.transport_types import (  # noqa: F401  (public re-exports)
    ProbeResult,
    TransportType,
    normalize_mcp_base_url,
)

logger = logging.getLogger(__name__)

PROBE_TIMEOUT_S = 5.0


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
