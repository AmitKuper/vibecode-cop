#!/usr/bin/env python3
"""Demo game: our cop (police) vs external sparring kit (thief) via reference-v3.

Usage:
    cd vibecode-cop
    python scripts/demo_vs_sparring.py [--kit-root PATH] [--sub-games N]

What this proves:
  - Our MCP server correctly registers the 4 reference-v3 tools
  - Sparring thief can call our tools and receive our turns
  - Our cop actively drives a full sub-game against sparring thief
  - Reference-v3 bidirectional game loop works end-to-end
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
KIT_ROOT = REPO_ROOT.parent / "external" / "copthief-league-protocol"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _check_port(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex((host, port)) == 0


async def _wait_port_async(host: str, port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _check_port(host, port):
            return
        await asyncio.sleep(0.15)
    raise TimeoutError(f"server did not listen on {host}:{port}")


def _stop(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(3)


async def _poll_deque(deque, *, timeout: float = 20.0, label: str) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if deque:
            return deque.popleft()
        await asyncio.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for {label} ({timeout}s)")


async def _poll_inbox_step(inbox, step: int, *, timeout: float = 20.0) -> None:
    """Wait until inbox has processed step."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if inbox.next_step > step:
            return
        await asyncio.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for inbox step {step}")


async def _game_loop(
    out_session,   # ReferenceV3Session connected to sparring (outbound)
    in_session,    # ReferenceV3Session served by our server (inbound from sparring)
    n_sub_games: int,
) -> list[dict]:
    """Run n_sub_games of cop-vs-thief reference-v3 sub-games."""
    from agent.adaptive.reference_v3 import (
        build_negotiation,
        build_turn,
        default_terms,
        verify_audit,
        verify_negotiation,
    )

    terms = default_terms()
    group_id = "vibecode-demo-cop"
    group_name = "Vibecode Demo Cop"
    board_size = terms["board_size"]
    max_steps = terms["max_steps"]
    results = []

    for sub_game_n in range(1, n_sub_games + 1):
        print(f"\n[demo] === Sub-game {sub_game_n}/{n_sub_games} (we are police) ===")
        nonce = secrets.token_hex(16)
        our_greeting = build_negotiation(
            terms=terms,
            nonce=nonce,
            group_id=group_id,
            group_name=group_name,
            role="police",
            sub_game_number=sub_game_n,
        )
        await out_session.send_negotiation(our_greeting)
        their_greeting = await _poll_deque(in_session.agreements, label="negotiate", timeout=30.0)
        negotiated = verify_negotiation(our_greeting, their_greeting)
        print(f"[demo]   Handshake OK — opponent={negotiated.opponent_group}")

        pos = list(terms.get("cop_start", [0, 0]))
        rng = random.Random(f"demo-{sub_game_n}")
        moves = ["N", "S", "E", "W", "STAY"]

        for step in range(1, max_steps + 1):
            if step % 5 == 1:
                print(f"[demo]   Step {step}/{max_steps}...", flush=True)
            # Reference-v3: THIEF moves first, then POLICE.
            # Wait for sparring thief's commitment before sending ours.
            await _poll_inbox_step(in_session.turns, step, timeout=20.0)

            move = rng.choice(moves)
            # Apply move first so the recorded position reflects where we land.
            # audit_records checks: position[N] - position[N-1] == delta(move[N]),
            # so position must be the post-move cell, not the pre-move cell.
            if move == "N" and pos[1] > 0:
                pos[1] -= 1
            elif move == "S" and pos[1] < board_size - 1:
                pos[1] += 1
            elif move == "E" and pos[0] < board_size - 1:
                pos[0] += 1
            elif move == "W" and pos[0] > 0:
                pos[0] -= 1
            record_payload = {
                "step": step,
                "role": "police",
                "sub_game": sub_game_n,
                "state": f"grid={board_size}x{board_size};self={pos};barriers=[]",
                "position": list(pos),
                "move": move,
                "intent": "truth",
                "hint": f"demo step {step}",
                "verdict": "moved",
            }
            smell_grid = {f"{pos[0]},{pos[1]}": max(0.0, 0.9 - step * 0.02)}
            step_nonce = secrets.token_hex(16)
            turn, record = build_turn(
                record_payload=record_payload,
                nonce=step_nonce,
                sender="police",
                hint=f"demo step {step}",
                smell_grid=smell_grid,
            )
            await out_session.send_turn(turn, record)

        print(f"[demo]   {max_steps} steps done — exchanging audits")
        await out_session.send_audit("police", "timeout")
        their_audit_payload = await _poll_deque(
            in_session.audits, label="submit_audit", timeout=30.0
        )
        ok, errors = verify_audit(their_audit_payload, dict(in_session.turns.played))
        print(f"[demo]   Audit: ok={ok} errors={errors[:3] if errors else []}")

        control_msg = {
            "kind": "done", "sender": "police",
            "sub_game_number": sub_game_n, "status": "complete",
            "step_budget": float(max_steps), "payload": {},
        }
        await out_session.send_control(control_msg)
        try:
            await _poll_deque(in_session.controls, label="receive_control", timeout=8.0)
        except TimeoutError:
            pass

        # Reset inbox for next sub-game
        from agent.adaptive.reference_v3 import ReferenceV3Inbox
        in_session.turns = ReferenceV3Inbox(window=4)

        results.append({"sub_game": sub_game_n, "steps": max_steps, "audit_ok": ok})
        print(f"[demo]   Sub-game {sub_game_n} complete")

    return results


async def _run_all(our_port: int, sparring_port: int, kit: Path, n_sub_games: int) -> dict:
    """Start server, then sparring, then play."""
    import json as _json
    from fastmcp import Client, FastMCP
    from fastmcp.client.transports import StreamableHttpTransport
    from agent.adaptive.pipeline import discover_reference_v3
    from agent.adaptive.reference_v3 import ReferenceV3Session, register_reference_v3_tools

    host = "127.0.0.1"
    our_mcp_url = f"http://{host}:{our_port}/mcp"
    sparring_url = f"http://{host}:{sparring_port}"
    sparring_mcp_url = f"{sparring_url}/mcp"

    # Inbound session — populated when sparring calls OUR tools
    in_session = ReferenceV3Session(lambda t, p: (_ for _ in ()).throw(
        RuntimeError(f"outbound not configured in server ({t})")
    ))

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
                sys.executable, "-m", "sparring.cli", "serve",
                "--role", "thief",
                "--port", str(sparring_port),
                "--host", host,
                "--peer", our_mcp_url,
                "--group-id", "sparring-demo-thief",
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
        try:
            await server_task
        except (asyncio.CancelledError, Exception):
            pass
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit-root", type=Path, default=KIT_ROOT)
    parser.add_argument("--our-port", type=int, default=5001)
    parser.add_argument("--sparring-port", type=int, default=8931)
    parser.add_argument("--sub-games", type=int, default=1)
    args = parser.parse_args()

    kit = args.kit_root.resolve()
    if not (kit / "verify_vectors.py").is_file():
        print(f"ERROR: not a league-protocol clone: {kit}")
        return 1

    try:
        result = asyncio.run(_run_all(args.our_port, args.sparring_port, kit, args.sub_games))
        print(f"\n[demo] === RESULT ===")
        print(json.dumps(result, indent=2))
        passed = sum(1 for sg in result["sub_games"] if sg.get("audit_ok") is not False)
        total = result["n"]
        status = "PASS" if passed == total else f"PARTIAL ({passed}/{total})"
        print(f"[demo] STATUS: {status}")
        return 0 if passed > 0 else 1
    except Exception as exc:
        print(f"[demo] ERROR: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
