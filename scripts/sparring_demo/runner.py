"""Server/sparring lifecycle: start our server, launch sparring, play, tear down."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

from sparring_demo.game_loop import _game_loop
from sparring_demo.netutil import _stop, _wait_port_async


async def _run_all(our_port: int, sparring_port: int, kit: Path, n_sub_games: int) -> dict:
    """Start server, then sparring, then play."""
    import json as _json

    from fastmcp import Client, FastMCP
    from fastmcp.client.transports import StreamableHttpTransport

    from cop_worker.protocol.pipeline import discover_reference_v3
    from cop_worker.protocol.reference_v3 import ReferenceV3Session, register_reference_v3_tools

    host = "127.0.0.1"
    our_mcp_url = f"http://{host}:{our_port}/mcp"
    sparring_url = f"http://{host}:{sparring_port}"
    sparring_mcp_url = f"{sparring_url}/mcp"

    # Inbound session — populated when sparring calls OUR tools
    in_session = ReferenceV3Session(
        lambda t, p: (_ for _ in ()).throw(RuntimeError(f"outbound not configured in server ({t})"))
    )

    # Start our SSE server as a background task
    app = FastMCP(name="vibecode-demo-cop")
    register_reference_v3_tools(app, in_session)
    server_task = asyncio.create_task(
        app.run_async(transport="http", host=host, port=our_port, show_banner=False)
    )

    # Wait for our server to be ready
    await _wait_port_async(host, our_port, timeout=15.0)
    print(f"[demo] Our cop server ready at {our_mcp_url}")

    sparring_proc = None
    try:
        # Start sparring thief server, telling it to connect to OUR SSE server
        sparring_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "sparring.cli",
                "serve",
                "--role",
                "thief",
                "--scent-model",
                "multiplicative_book_v1",
                "--port",
                str(sparring_port),
                "--host",
                host,
                "--peer",
                our_mcp_url,
                "--group-id",
                "sparring-demo-thief",
                "--await-peer",
            ],
            cwd=kit,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        await _wait_port_async(host, sparring_port, timeout=30.0)
        print(f"[demo] Sparring thief ready at {sparring_url}")
        # Give sparring a moment to fully initialize its game loop
        await asyncio.sleep(2.0)

        # Open a PERSISTENT MCP session to sparring's streamable-http server.
        # Sparring's server is session-oriented: each new Client.__aenter__ establishes a
        # fresh MCP session, and creating one per call (the pipeline default) re-initialises
        # too often and hits httpx.ReadTimeout after a few steps. One session for the whole
        # game avoids that.
        print(f"[demo] Connecting persistent session to sparring at {sparring_mcp_url}...")
        sparring_transport = StreamableHttpTransport(sparring_mcp_url)
        async with Client(sparring_transport) as sparring_client:

            def _make_caller(client):
                async def _call(tool_name: str, params: dict) -> dict:
                    result = await client.call_tool(tool_name, params)
                    if not result.content:
                        return {"ok": getattr(result, "is_error", False) is not True}
                    item = result.content[0]
                    value = item.text if hasattr(item, "text") else str(item)
                    if getattr(result, "is_error", False):
                        return {"ok": False, "error": value}
                    try:
                        parsed = _json.loads(value)
                    except (ValueError, TypeError):
                        return {"ok": True, "raw": value}
                    return parsed if isinstance(parsed, dict) else {"ok": True, "raw": parsed}

                return _call

            _profile, out_session = await discover_reference_v3(
                sparring_url, tool_caller=_make_caller(sparring_client)
            )
            print(f"[demo] Profile locked: {_profile.profile_hash[:16]}...")

            results = await _game_loop(out_session, in_session, n_sub_games)

    finally:
        server_task.cancel()
        import contextlib

        with contextlib.suppress(asyncio.CancelledError, Exception):
            await server_task
        if sparring_proc:
            sparring_proc.terminate()
            try:
                out_bytes, _ = sparring_proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                sparring_proc.kill()
                out_bytes, _ = sparring_proc.communicate(timeout=5)
            if out_bytes:
                sparring_out = out_bytes.decode(errors="replace")
                print(f"\n[sparring output (last 2000 chars)]\n...{sparring_out[-2000:]}")
        _stop(sparring_proc)

    return {"sub_games": results, "n": n_sub_games}
