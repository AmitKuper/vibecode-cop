"""Peer session-churn regression: our inbound door must survive a client that
opens a session, uses it, CLOSES it (DELETE), and re-dials — per window, like
real league peers do (najamjad, 2026-08-13: the door wedged after exactly this;
the kit's sparring client never closes sessions, so self-tests missed it).

Also pins the door_guard probe/rebuild path used as the production self-heal.
"""

from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_door_survives_session_open_use_delete_redial_cycles():
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport
    from ref3_match.servers import _start_server_one

    port = _free_port()

    async def run():
        session, task = await _start_server_one("127.0.0.1", port, "thief")
        try:
            for window in range(1, 4):  # three windows of churn: open → use → DELETE → redial
                transport = StreamableHttpTransport(f"http://127.0.0.1:{port}/mcp")
                async with Client(transport, timeout=10) as client:
                    tools = await client.list_tools()
                    assert {t.name for t in tools} >= {"negotiate", "receive_turn"}
                    reply = await client.call_tool(
                        "negotiate", {"message": {"sub_game_number": window, "role": "police"}}
                    )
                    assert reply is not None
                # context exit closed the session (DELETE); next loop re-dials fresh
            assert len(session.agreements) == 3  # every window's greeting landed
        finally:
            task.cancel()
            import contextlib

            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    asyncio.run(run())


def test_door_guard_probe_healthy_and_rebuild_path():
    from ref3_match.door_guard import _door_answers, ensure_door_answers
    from ref3_match.servers import _start_server_one

    port = _free_port()

    async def run():
        session, task = await _start_server_one("127.0.0.1", port, "police")
        try:
            assert await _door_answers(port)  # healthy door answers the probe
            same_session, task2 = await ensure_door_answers(
                "police", {"port": port, "host": "127.0.0.1"}, session, task
            )
            assert same_session is session  # healthy path: nothing rebuilt
            # Now kill the server: the probe must detect silence and rebuild.
            task2.cancel()
            import contextlib

            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task2
            await asyncio.sleep(0.3)
            rebuilt_session, task3 = await ensure_door_answers(
                "police", {"port": port, "host": "127.0.0.1"}, session, task2
            )
            assert rebuilt_session is session  # SAME session survives the rebuild
            assert await _door_answers(port)  # and the door answers again
            task3.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task3
        finally:
            pass

    asyncio.run(run())
