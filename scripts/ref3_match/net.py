"""Networking primitives: port checks, inbox polling, endpoint awaiting."""

from __future__ import annotations

import asyncio
import socket
import time


def _check_port(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex((host, port)) == 0


async def _wait_port(host: str, port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _check_port(host, port):
            return
        await asyncio.sleep(0.15)
    raise TimeoutError(f"no listener on {host}:{port}")


class NoGameHappenedError(TimeoutError):
    """A window failure BEFORE any opponent step arrived.

    Index-hold rule (agreed with uoh-sqak, 2026-08-12): a sub-game in which no
    game actually happened — discovery failed, no matching greeting, or the peer
    handshook and then never played a step — must NOT spend its index. The
    series loop retries the same number, bounded by time, so a holding peer can
    converge onto it. A window that died AFTER steps were exchanged is spent as
    before (replaying a partially played index would corrupt the audit story).
    """


async def _poll_deque(dq, *, timeout: float, label: str) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if dq:
            return dq.popleft()
        await asyncio.sleep(0.05)
    raise TimeoutError(f"timeout waiting for {label}")


async def _poll_agreement(dq, sub_game: int, *, timeout: float) -> dict:
    """Return the peer greeting whose sub_game_number matches, discarding stale ones.

    The peer re-dials our negotiate across per-window re-runs, so greetings pile up in
    the deque. Consuming FIFO makes us pick a stale greeting (its sub_game lags ours) →
    SPAR-N06. Instead we match by sub_game_number: drop older greetings, keep newer.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        keep, found = [], None
        while dq:
            msg = dq.popleft()
            n = msg.get("sub_game_number")
            if found is None and (n == sub_game or not isinstance(n, int)):
                found = msg
            elif isinstance(n, int) and n < sub_game:
                continue  # drop stale greeting from an earlier sub-game
            else:
                keep.append(msg)  # a greeting for a later sub-game — keep it
        dq.extend(keep)
        if found is not None:
            return found
        await asyncio.sleep(0.05)
    raise NoGameHappenedError(f"timeout waiting for negotiate matching sub_game {sub_game}")


async def _poll_turn(inbox, step: int, *, timeout: float, session=None) -> dict:
    """Wait until the inbox has the opponent's turn for `step`; return it.

    On timeout the error carries the diagnosis a stalled peer needs: which step we
    were owed, which steps actually played, and the peer's last inbound turn — the
    "your step k never arrived; your last was k-1 at HH:MM:SS" line that separates
    OUR stall from THEIRS in one read.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if step in inbox.played or inbox.next_step > step:
            return inbox.turn_for(step) if hasattr(inbox, "turn_for") else {}
        await asyncio.sleep(0.05)
    played = sorted(inbox.played)
    last = None
    if session is not None and getattr(session, "turn_messages", None):
        m = session.turn_messages[-1]
        last = (m.get("step"), m.get("sender"), str(m.get("timestamp"))[:23])
    # Zero opponent steps ever = a zero-turn window (never settles, files no row):
    # retriable at the same index. Any played step means the game truly started.
    err_cls = NoGameHappenedError if not played else TimeoutError
    raise err_cls(
        f"timeout after {timeout:.0f}s waiting for opponent turn step {step}; "
        f"steps played={played or 'none'}, buffered={sorted(inbox.buffered) or 'none'}, "
        f"their last inbound turn={last or 'NONE EVER'}"
    )


async def _await_endpoint(mcp_url: str, client_cls, *, window_s: float = 900.0) -> bool:
    """Poll ONE peer MCP URL until it answers list_tools (its window opens), or timeout.

    The peer binds its cop/thief endpoint only during that role's sub-game window, so we
    wait for the specific endpoint we must dial and tolerate transient 502/530/refused
    (its origin is down between windows) rather than treating them as fatal.
    """
    deadline = time.monotonic() + window_s
    announced = False
    while time.monotonic() < deadline:
        try:
            async with client_cls(mcp_url) as c:
                await c.list_tools()
            print(f"[match] peer endpoint UP: {mcp_url}")
            return True
        except Exception as exc:
            if not announced:
                print(
                    f"[match] waiting for peer endpoint {mcp_url} "
                    f"({type(exc).__name__}: {str(exc)[:80]})"
                )
                announced = True
            await asyncio.sleep(8)
    return False


def _latest_turn(in_session, step: int) -> dict:
    for t in reversed(in_session.turn_messages):
        if int(t.get("step", -1)) == step:
            return t
    return {}
