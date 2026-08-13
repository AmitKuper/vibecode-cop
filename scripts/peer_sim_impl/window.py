"""One window over the real wire: dial, greet (with quirks), play, audit, DELETE.

The window opens a FRESH MCP client session to the correct vibecode door and —
critically — closes it cleanly at window end: the streamable-http client context
exit sends the session DELETE that wedged our thief door in a live game. That
DELETE is the whole point of this simulator; it must fire every window.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import random

from cop_worker.protocol.reference_v3 import verify_negotiation
from peer_sim_impl.window_cop import play_cop_window
from peer_sim_impl.window_thief import play_thief_window


def _caller(client):
    async def call(tool: str, params: dict) -> dict:
        result = await client.call_tool(tool, params)
        content = getattr(result, "content", None) or []
        text = getattr(content[0], "text", "") if content else ""
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            return {"ok": True}
        return parsed if isinstance(parsed, dict) else {"ok": True}

    return call


async def _eager_greeting(call, lean_next: dict, window: int) -> None:
    """Quirk (a): ~2s in, send the NEXT window's greeting to the CURRENT door.

    For that next window this is usually the WRONG door — exactly how a
    single-URL peer behaves — which exercises vibecode's greeting relay
    (drain/bank/inject through the orchestrator).
    """
    await asyncio.sleep(2.0)
    with contextlib.suppress(Exception):
        await call("negotiate", {"message": lean_next})
        print(
            f"[peersim] w{window} EAGER greeting for w{window + 1} sent to current door",
            flush=True,
        )


async def _duplicate_greetings(call, lean: dict, window: int) -> None:
    """Quirk (b): re-send our greeting every ~5s while waiting (same bytes)."""
    while True:
        await asyncio.sleep(5.0)
        with contextlib.suppress(Exception):
            await call("negotiate", {"message": lean})
            print(f"[peersim] w{window} duplicate greeting re-sent", flush=True)


async def _settle_window(call, inbox, *, window, role, records, claim, max_steps) -> None:
    """Audit + done control, then a short best-effort wait for THEIR audit."""
    await call(
        "submit_audit",
        {"payload": {"sender": role, "records": records, "result_claim": claim}},
    )
    await call(
        "receive_control",
        {
            "message": {
                "kind": "done",
                "sender": role,
                "sub_game_number": window,
                "status": "complete",
                "step_budget": float(max_steps),
                "payload": {},
            }
        },
    )
    theirs = await inbox.wait_audit(timeout=15.0)
    got = f"received ({len((theirs or {}).get('records') or [])} records)" if theirs else "not seen"
    print(f"[peersim] w{window} audit sent ({claim}); their audit {got}", flush=True)


async def run_window(*, window, role, door_url, terms, inbox, greetings, flags) -> None:
    """Drive one full window through a fresh client session; always DELETEs on exit."""
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    if flags["slow_dial"]:
        delay = random.uniform(3.0, 8.0)
        print(f"[peersim] w{window} waiting {delay:.1f}s before dialing (slow peer)", flush=True)
        await asyncio.sleep(delay)
    inbox.reset_window()
    full, lean = greetings[window]
    dup_task = eager_task = None
    print(f"[peersim] w{window} role={role} dialing {door_url}", flush=True)
    async with Client(StreamableHttpTransport(door_url), timeout=10.0) as client:
        call = _caller(client)
        try:
            await call("negotiate", {"message": lean})
            if flags["duplicate_greeting"]:
                dup_task = asyncio.create_task(_duplicate_greetings(call, lean, window))
            if flags["eager_greeting"] and window < 6:
                eager_task = asyncio.create_task(
                    _eager_greeting(call, greetings[window + 1][1], window)
                )
            theirs = await inbox.wait_greeting(window, timeout=flags["greeting_timeout"])
            if dup_task is not None:
                dup_task.cancel()
            verify_negotiation(full, theirs)
            opp = (theirs.get("identity") or {}).get("group_id") or theirs.get("group_id")
            print(f"[peersim] w{window} handshake OK vs {opp}", flush=True)
            play = play_cop_window if role == "police" else play_thief_window
            records, claim = await play(
                call, inbox, sub_game=window, terms=terms, turn_timeout=flags["turn_timeout"]
            )
            await _settle_window(
                call,
                inbox,
                window=window,
                role=role,
                records=records,
                claim=claim,
                max_steps=int(terms["max_steps"]),
            )
        finally:
            for task in (dup_task, eager_task):
                if task is not None:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task
    # The context exit above closed the streamable-http session: DELETE sent.
    print(f"[peersim] w{window} MCP session closed (DELETE sent to door)", flush=True)
