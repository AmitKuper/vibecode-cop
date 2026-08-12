"""Hold both reference-v3 endpoints up for an opponent's reachability probe.

Serves the real cop+thief MCP endpoints (same registration path as a match) on
0.0.0.0 and idles until killed. NOT a game: the outbound caller throws, so any
turn traffic fails loudly. KILL THIS before launching a real match — the match
port preflight refuses to start while these ports are held.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ref3_match.servers import _preflight_ports, _start_servers  # noqa: E402


async def main() -> None:
    cop_port, thief_port = 61224, 61223
    _preflight_ports(cop_port, thief_port)
    await _start_servers("0.0.0.0", cop_port, thief_port)
    print(
        f"[probe-hold] endpoints LIVE on 0.0.0.0:{cop_port} (cop) / :{thief_port} (thief)",
        flush=True,
    )
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
