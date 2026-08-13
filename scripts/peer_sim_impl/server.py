"""The peersim single-port FastMCP server: four reference-v3 tools, superset schema.

One app on ONE port serves all six windows (single-URL peer, the najamjad and
uoh-sqak shape). Every tool advertises the SUPERSET schema najamjad showed us:
BOTH ``message`` and ``payload`` properties, object-typed, none required.
"""

from __future__ import annotations

import asyncio

from pydantic import Field

from peer_sim_impl.inbox import PeerInbox

#: Shared optional-object field: yields the najamjad schema shape — property
#: {"type": "object"} with no required list (safe to share: annotations all dict).
_OBJ = Field(default_factory=dict)


def build_app(inbox: PeerInbox):
    """Build the FastMCP app; every inbound call lands in ``inbox``."""
    from fastmcp import FastMCP

    app = FastMCP(name="peersim01")

    @app.tool
    def negotiate(
        message: dict = _OBJ,
        payload: dict = _OBJ,
    ) -> dict:
        """Receive the opponent's signed game agreement."""
        msg = message or payload
        print(
            f"[peersim<-] negotiate sub_game={msg.get('sub_game_number')} role={msg.get('role')}",
            flush=True,
        )
        inbox.add_greeting(msg)
        return {"ok": True}

    @app.tool
    def receive_turn(
        message: dict = _OBJ,
        payload: dict = _OBJ,
    ) -> dict:
        """Receive the opponent's sealed turn message."""
        msg = message or payload
        inbox.turns.append(dict(msg))
        print(
            f"[peersim<-] turn step={msg.get('step')} sender={msg.get('sender')}",
            flush=True,
        )
        return {"ok": True}

    @app.tool
    def submit_audit(
        payload: dict = _OBJ,
        message: dict = _OBJ,
    ) -> dict:
        """Receive the opponent's end-of-game audit reveal (records + nonces)."""
        msg = payload or message
        inbox.audits.append(dict(msg))
        n_records = len(msg.get("records") or [])
        print(
            f"[peersim<-] audit sender={msg.get('sender')} records={n_records} "
            f"claim={msg.get('result_claim')}",
            flush=True,
        )
        return {"ok": True}

    @app.tool
    def receive_control(
        message: dict = _OBJ,
        payload: dict = _OBJ,
    ) -> dict:
        """Receive an opponent control signal (done / status / restart / quit)."""
        msg = message or payload
        inbox.controls.append(dict(msg))
        print(f"[peersim<-] control kind={msg.get('kind')}", flush=True)
        return {"ok": True}

    return app


async def start_server(inbox: PeerInbox, host: str, port: int) -> asyncio.Task:
    """Serve the app; returns the server task (cancel it to shut down)."""
    from ref3_match.net import _wait_port

    app = build_app(inbox)
    task = asyncio.create_task(
        app.run_async(transport="http", host=host, port=port, show_banner=False)
    )
    await _wait_port("127.0.0.1", port, timeout=20.0)
    print(f"[peersim] serving ALL windows on http://{host}:{port}/mcp", flush=True)
    return task
