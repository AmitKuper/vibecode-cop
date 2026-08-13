"""Pre-game protocol probe: run against a new opponent's LIVE endpoint before any T.

Usage:
    python scripts/preflight_opponent.py <mcp_url> [<mcp_url_2>]

For each URL: transport reachability, tools/list introspection (names + argument
properties), and our real reference-v3 discovery — printing ACCEPT or the exact
refusal reason. Thirty seconds here would have caught the najamjad surface
refusal hours before T (2026-08-13). Run it the moment a pairing's endpoint
first comes up, and again at T-10.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def _probe(url: str) -> bool:
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    from cop_worker.protocol.pipeline import discover_reference_v3

    mcp_url = url if url.endswith("/mcp") else url.rstrip("/") + "/mcp"
    base_url = mcp_url.removesuffix("/mcp")
    print(f"\n=== {mcp_url} ===")
    try:
        async with Client(StreamableHttpTransport(mcp_url), timeout=15) as client:
            tools = await client.list_tools()
            print(f"reachable; {len(tools)} tools advertised:")
            for t in sorted(tools, key=lambda x: x.name):
                schema = t.inputSchema or {}
                props = list((schema.get("properties") or {}).keys())
                req = schema.get("required") or []
                print(f"  {t.name}({', '.join(props)})  required={req}")
    except Exception as exc:
        print(f"UNREACHABLE / no MCP answer: {type(exc).__name__}: {str(exc)[:160]}")
        return False
    try:
        profile, _session = await discover_reference_v3(
            base_url, probe_timeout_s=20, introspect_timeout_s=20
        )
        print(f"DISCOVERY: ACCEPT — reference-v3 profile ok (digest {profile.schema_digest[:12]})")
        return True
    except Exception as exc:
        print(f"DISCOVERY: REFUSE — {type(exc).__name__}: {str(exc)[:200]}")
        return False


def main() -> int:
    urls = sys.argv[1:]
    if not urls:
        print("Usage: python scripts/preflight_opponent.py <mcp_url> [<mcp_url_2>]")
        return 2
    results = [asyncio.run(_probe(u)) for u in urls]
    ok = all(results)
    print(f"\nVERDICT: {'READY — discovery accepts every endpoint' if ok else 'NOT READY'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
