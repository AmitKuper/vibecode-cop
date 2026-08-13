"""Inbound-door self-heal for a role worker (live finding vs najamjad, 2026-08-13).

Wedge signature: after a peer closes its MCP session, the streamable-http layer
can stop answering — the kernel accepts TCP but no request ever completes, so the
peer's dials read-time-out while our own outbound play continues fine. Before
each window the worker probes its own door; on silence it rebuilds the HTTP stack
around the SAME session object, so banked greetings survive the rebuild.
"""

from __future__ import annotations

import asyncio
import contextlib


async def _door_answers(port: int, timeout_s: float = 3.0) -> bool:
    """True if our own inbound door produces ANY HTTP response (even an error)."""
    import httpx

    body = {"jsonrpc": "2.0", "id": 0, "method": "ping"}
    headers = {"Accept": "application/json, text/event-stream"}
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            await client.post(f"http://127.0.0.1:{port}/mcp", json=body, headers=headers)
        return True
    except httpx.TimeoutException:
        return False
    except Exception:
        return True  # a transport-level rejection is still an ANSWERING stack


async def ensure_door_answers(role: str, init: dict, session, server_task):
    """Probe; rebuild the server around the same session if wedged.

    Returns ``(session, server_task)`` — unchanged when healthy.
    """
    from ref3_match.servers import _start_server_one

    port = int(init["port"])
    if await _door_answers(port):
        return session, server_task
    print(f"[{role}-worker] inbound door unresponsive — rebuilding server")
    server_task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await server_task
    await asyncio.sleep(0.5)  # let the OS release the port
    session, server_task = await _start_server_one(
        init.get("host", "0.0.0.0"), port, role, session=session
    )
    print(f"[{role}-worker] server rebuilt on :{port}")
    return session, server_task
