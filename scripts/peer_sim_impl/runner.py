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


async def _drive_window(window: int, *, doors, terms, inbox, greetings, flags) -> bool:
    from ref3_match.net import _wait_port

    role = role_for(window)
    # peersim cop dials the vibecode THIEF door; peersim thief dials the COP door.
    door_port = doors["thief" if role == "police" else "cop"]
    door_url = f"http://127.0.0.1:{door_port}/mcp"
    # Real peers poll patiently until the door exists (vibecode may start later).
    try:
        await _wait_port("127.0.0.1", door_port, timeout=flags["greeting_timeout"])
    except TimeoutError:
        print(f"[peersim] w{window} vibecode door :{door_port} never opened", flush=True)
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
    doors = {
        "cop": int(net.get("our_cop_port", 61224)),
        "thief": int(net.get("our_thief_port", 61223)),
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
