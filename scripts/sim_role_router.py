"""Sim-only MCP shim: route the single-URL sparring peer to our role-split ports.

The kit's sparring peer pushes everything to ONE --peer URL; a real league opponent
(imreeyal) dials our POLICE endpoint when its thief plays and our THIEF endpoint when
its police plays. This shim restores that: it inspects each message's sender role and
forwards to the matching backend — police-sent traffic to our thief session (:61223),
thief-sent traffic to our police session (:61224).
"""

import asyncio
import json
import sys

from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport

OUR_POLICE = "http://127.0.0.1:61224/mcp"  # serves OUR cop  (peer's thief dials it)
OUR_THIEF = "http://127.0.0.1:61223/mcp"   # serves OUR thief (peer's police dials it)


def _target(sender: str | None) -> str:
    return OUR_THIEF if sender == "police" else OUR_POLICE


async def _forward(tool: str, arg_name: str, payload: dict, sender: str | None) -> dict:
    url = _target(sender)
    transport = StreamableHttpTransport(url)
    async with Client(transport, timeout=15) as client:
        r = await client.call_tool(tool, {arg_name: payload})
        if not r.content:
            return {"ok": True}
        text = getattr(r.content[0], "text", "")
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {"ok": True}
        except (ValueError, TypeError):
            return {"ok": True, "raw": text}


app = FastMCP(name="role-router-shim")


@app.tool()
async def negotiate(message: dict) -> dict:
    return await _forward("negotiate", "message", message, (message or {}).get("role"))


@app.tool()
async def receive_turn(message: dict) -> dict:
    return await _forward("receive_turn", "message", message, (message or {}).get("sender"))


@app.tool()
async def submit_audit(payload: dict) -> dict:
    return await _forward("submit_audit", "payload", payload, (payload or {}).get("sender"))


@app.tool()
async def receive_control(message: dict) -> dict:
    return await _forward("receive_control", "message", message, (message or {}).get("sender"))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8940
    asyncio.run(app.run_async(transport="http", host="127.0.0.1", port=port,
                              show_banner=False))
