"""peersim entry logic: start the one-port server, then drive windows 1..6 as client.

Window failures retry the SAME window a few times (mirroring vibecode's
index-hold convergence rule) with a shorter greeting wait — a holding vibecode
re-sends a fresh greeting within seconds; a silent one means it spent the index
and we move on too.
"""

from __future__ import annotations

import asyncio
import contextlib

from peer_sim_impl.greetings import make_greetings, make_terms, role_for
from peer_sim_impl.inbox import PeerInbox
from peer_sim_impl.server import start_server
from peer_sim_impl.window import run_window

_RETRIES_PER_WINDOW = 3


async def _door_up(door_url: str, timeout_s: float) -> bool:
    """Poll a vibecode door until it answers: TCP for localhost, HTTP for tunnels."""
    import asyncio as _asyncio
    import time as _time

    from ref3_match.net import _check_port

    local = "127.0.0.1" in door_url or "localhost" in door_url
    port = int(door_url.rsplit(":", 1)[1].split("/")[0]) if local else 0
    deadline = _time.monotonic() + timeout_s
    while _time.monotonic() < deadline:
        if local:
            if _check_port("127.0.0.1", port):
                return True
        else:
            import httpx

            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    await client.get(door_url)
                return True  # any HTTP status = the tunnel + door answer
            except Exception:
                pass
        await _asyncio.sleep(2.0)
    return False


async def _drive_window(window: int, *, doors, terms, inbox, greetings, flags) -> bool:

    role = role_for(window)
    # peersim cop dials the vibecode THIEF door; peersim thief dials the COP door.
    door_url = doors["thief" if role == "police" else "cop"]
    # Real peers poll patiently until the door exists (vibecode may start later).
    # Local doors: TCP poll. Tunnel doors (ngrok/cloudflared): any HTTP answer = up.
    if not await _door_up(door_url, flags["greeting_timeout"]):
        print(f"[peersim] w{window} vibecode door {door_url} never opened", flush=True)
        return False
    opponent_sender = "thief" if role == "police" else "police"
    try:
        for attempt in range(1 + _RETRIES_PER_WINDOW):
            window_flags = dict(flags)
            if attempt:  # retry: a holding vibecode re-greets within seconds
                window_flags["greeting_timeout"] = min(60.0, flags["greeting_timeout"])
            try:
                await run_window(
                    window=window,
                    role=role,
                    door_url=door_url,
                    terms=terms,
                    inbox=inbox,
                    greetings=greetings,
                    flags=window_flags,
                )
                return True
            except Exception as exc:
                print(
                    f"[peersim] w{window} attempt {attempt + 1} FAILED "
                    f"({type(exc).__name__}: {str(exc)[:140]})",
                    flush=True,
                )
        print(f"[peersim] w{window} exhausted retries — moving on", flush=True)
        return False
    finally:
        # End-of-window turn purge (see PeerInbox.purge_sender): the NEXT window
        # with this sender must never match this window's stale steps.
        inbox.purge_sender(opponent_sender)


async def run_sim(args) -> int:
    """The simulator's whole life: serve one URL, play six windows, linger, exit."""
    from cop_worker.config_loader import load_runtime

    net = load_runtime(args.config).get("network", {})
    # Doors are full URLs: CLI overrides (tunnel testing) beat the profile's local ports.
    doors = {
        "cop": getattr(args, "cop_door_url", None)
        or f"http://127.0.0.1:{int(net.get('our_cop_port', 61224))}/mcp",
        "thief": getattr(args, "thief_door_url", None)
        or f"http://127.0.0.1:{int(net.get('our_thief_port', 61223))}/mcp",
    }
    inbox = PeerInbox()
    server_task = await start_server(inbox, args.host, args.port)
    terms = make_terms(args.config)
    greetings = make_greetings(terms)
    flags = {
        "slow_dial": not args.no_slow_dial,
        "duplicate_greeting": not args.no_duplicate_greeting,
        "eager_greeting": not args.no_eager_greeting,
        "greeting_timeout": args.greeting_timeout,
        "turn_timeout": args.turn_timeout,
    }
    print(
        f"[peersim] group={args.config!r} profile doors cop:{doors['cop']} "
        f"thief:{doors['thief']} quirks: eager={flags['eager_greeting']} "
        f"duplicate={flags['duplicate_greeting']} slow_dial={flags['slow_dial']}",
        flush=True,
    )
    failures = 0
    try:
        for window in range(1, args.windows + 1):
            ok = await _drive_window(
                window, doors=doors, terms=terms, inbox=inbox, greetings=greetings, flags=flags
            )
            failures += 0 if ok else 1
        print(
            f"[peersim] all windows done ({failures} failed); lingering 15s for late traffic",
            flush=True,
        )
        await asyncio.sleep(15.0)
    finally:
        server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await server_task
    return 1 if failures else 0
