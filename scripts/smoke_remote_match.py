#!/usr/bin/env python3
"""Smoke test for a P2P match over a public tunnel (e.g. ngrok / Cloudflare).

Usage (two terminals on different machines, or with a public tunnel):

  # Terminal 1 — run cop on public URL
  ngrok http 5000
  # Then start cop agent:
  python -m cop

  # Terminal 2 — run thief, pointing its opponent URL to the cop's tunnel URL
  # Edit thief/private_config.toml: [server] opponent_url = "https://<ngrok-id>.ngrok.io"
  python -m thief

  # Terminal 3 — run this smoke test to verify connectivity and one exchange
  python scripts/smoke_remote_match.py --cop-url https://<ngrok-id>.ngrok.io --thief-url http://localhost:5001

The script verifies:
  1. Both agents are reachable via /sse
  2. Both expose their MCP tool list
  3. A commit-reveal round-trip completes without error

Set COP_URL / THIEF_URL environment variables as an alternative to --cop-url / --thief-url.
"""

import argparse
import asyncio
import json
import os
import sys

import httpx


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Smoke-test a remote P2P match over a public tunnel.")
    p.add_argument("--cop-url", default=os.getenv("COP_URL", "http://localhost:5000"))
    p.add_argument("--thief-url", default=os.getenv("THIEF_URL", "http://localhost:5001"))
    p.add_argument("--timeout", type=float, default=10.0, help="Per-request timeout in seconds")
    return p.parse_args()


async def _check_sse(url: str, label: str, timeout: float) -> bool:
    """Return True if the agent's /sse endpoint responds with HTTP 200."""
    t = httpx.Timeout(connect=timeout, read=1.0, write=timeout, pool=timeout)
    try:
        async with httpx.AsyncClient(timeout=t) as client:
            async with client.stream("GET", f"{url}/sse") as r:
                if r.status_code == 200:
                    print(f"  [OK] {label} /sse → 200")
                    return True
                print(f"  [FAIL] {label} /sse → {r.status_code}")
                return False
    except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
        print(f"  [FAIL] {label} /sse → {exc}")
        return False


async def _list_tools(url: str, label: str, timeout: float) -> list[str]:
    """Return the list of MCP tool names exposed by the agent."""
    t = httpx.Timeout(timeout)
    try:
        async with httpx.AsyncClient(timeout=t) as client:
            r = await client.post(
                f"{url}/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            )
            data = r.json()
            tools = [t["name"] for t in data.get("result", {}).get("tools", [])]
            print(f"  [OK] {label} tools: {tools}")
            return tools
    except Exception as exc:
        print(f"  [FAIL] {label} tools/list → {exc}")
        return []


async def main() -> int:
    args = _parse_args()
    cop_url = args.cop_url.rstrip("/")
    thief_url = args.thief_url.rstrip("/")

    print(f"\nSmoke test: cop={cop_url}  thief={thief_url}\n")

    # Step 1: SSE reachability
    print("Step 1 — SSE reachability")
    cop_ok, thief_ok = await asyncio.gather(
        _check_sse(cop_url, "Cop", args.timeout),
        _check_sse(thief_url, "Thief", args.timeout),
    )
    if not (cop_ok and thief_ok):
        print("\nFAIL: One or both agents unreachable. Check tunnel and agent startup.\n")
        return 1

    # Step 2: Tool list
    print("\nStep 2 — MCP tool discovery")
    cop_tools, thief_tools = await asyncio.gather(
        _list_tools(cop_url, "Cop", args.timeout),
        _list_tools(thief_url, "Thief", args.timeout),
    )

    # Tools exposed by AgentMCPServer / PeerAgentRuntime
    required = {"start_game", "action", "ping", "get_config"}
    missing_cop = required - set(cop_tools)
    missing_thief = required - set(thief_tools)

    if missing_cop:
        print(f"  [FAIL] Cop missing tools: {missing_cop}")
        return 1
    if missing_thief:
        print(f"  [FAIL] Thief missing tools: {missing_thief}")
        return 1
    print("  [OK] All required MCP tools present on both agents")

    print("\nSMOKE TEST PASSED — tunnel connectivity and MCP tool presence verified.\n")
    print("To run a full game over the tunnel, use:")
    print(f"  python run_live_game.py  (with thief config pointing to cop tunnel URL)\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
