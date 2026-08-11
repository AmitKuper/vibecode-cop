"""Self-test harness: play vs the kit's local sparring peer."""

from __future__ import annotations

import asyncio
import contextlib
import json as _json
import subprocess
import sys
from pathlib import Path

from ref3_match.match_log import _wire_session_class
from ref3_match.net import _wait_port
from ref3_match.subgame import _play_subgame


def _plain_caller(c):
    async def _call(tool: str, params: dict) -> dict:
        r = await c.call_tool(tool, params)
        if not r.content:
            return {"ok": getattr(r, "is_error", False) is not True}
        val = getattr(r.content[0], "text", str(r.content[0]))
        try:
            parsed = _json.loads(val)
        except (ValueError, TypeError):
            return {"ok": True, "raw": val}
        return parsed if isinstance(parsed, dict) else {"ok": True}

    return _call


async def _self_test(
    role: str,
    sub_games: int,
    our_port: int,
    sparring_port: int,
    kit: Path,
    scent_model: str = "multiplicative_book_v1",
    move_policy: str = "rl",
) -> dict:
    from fastmcp import Client, FastMCP
    from fastmcp.client.transports import StreamableHttpTransport

    from cop_worker.protocol.pipeline import discover_reference_v3
    from cop_worker.protocol.reference_v3 import (
        default_terms,
        register_reference_v3_tools,
    )

    host = "127.0.0.1"
    our_url = f"http://{host}:{our_port}/mcp"
    sparring_url = f"http://{host}:{sparring_port}"
    # Sparring default setting is "Haifa"; match it for the self-test.
    terms = default_terms({"setting": "Haifa"})
    # Sparring takes the OPPOSITE role in sub-game 1.
    sparring_role = "police" if role == "thief" else "thief"

    in_session = _wire_session_class()(
        lambda t, p: (_ for _ in ()).throw(RuntimeError(f"no outbound on server ({t})"))
    )
    app = FastMCP(name="vibecode-match")
    register_reference_v3_tools(app, in_session)
    server_task = asyncio.create_task(
        app.run_async(transport="http", host=host, port=our_port, show_banner=False)
    )
    await _wait_port(host, our_port, timeout=15.0)
    print(f"[match] our reference-v3 server ready at {our_url} (role={role})")

    sparring = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "sparring.cli",
            "serve",
            "--role",
            sparring_role,
            "--scent-model",
            scent_model,
            "--port",
            str(sparring_port),
            "--host",
            host,
            "--peer",
            our_url,
            "--group-id",
            "sparring-match",
            "--await-peer",
        ],
        cwd=kit,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    results = []
    try:
        await _wait_port(host, sparring_port, timeout=30.0)
        await asyncio.sleep(2.0)
        transport = StreamableHttpTransport(f"{sparring_url}/mcp")
        async with Client(transport) as client:
            _profile, out_session = await discover_reference_v3(
                sparring_url, tool_caller=_plain_caller(client)
            )
            other = {"police": "thief", "thief": "police"}
            for sg in range(1, sub_games + 1):
                # Roles alternate every sub-game; our sub-game-1 role is `role`.
                sg_role = role if sg % 2 == 1 else other[role]
                results.append(
                    await _play_subgame(
                        out_session,
                        in_session,
                        role=sg_role,
                        sub_game=sg,
                        group_id="vibecode",
                        group_name="vibecode",
                        terms=terms,
                        opponent_group_hint="sparring-match",
                        scent_model=scent_model,
                        move_policy=move_policy,
                    )
                )
    finally:
        server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await server_task
        sparring.terminate()
        with contextlib.suppress(Exception):
            sparring.wait(timeout=8)
    return {"role": role, "sub_games": results}
