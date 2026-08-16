"""Keep a verified sub-game even if the peer's endpoint dies a moment later.

Twice against nis-yar1 (2026-08-12 and 2026-08-16) sub-game 5's audit passed and
their cloudflared tunnel returned 502 in the SAME millisecond. The row existed,
the exception discarded it, and a won window was filed as a failure - which cost
the whole series a report, because the settlement guard rightly refuses to file
5/6. The orchestrator's teardown-noise absorption could not help: the row never
left the worker process.

So the row is stashed the instant it exists, and the worker returns it even when
a later step raises. Cleared at every window start so a previous window's row can
never answer for this one.
"""

from __future__ import annotations


def remember(session, row: dict) -> None:
    """Record a settled row on the shared session as soon as it is built."""
    session._settled_row = row


def forget(session) -> None:
    """Clear at window start; a stale row must never stand in for a new window."""
    session._settled_row = None


def recover(session, sub_game: int) -> dict | None:
    """The settled row for `sub_game` if this window already settled, else None."""
    row = getattr(session, "_settled_row", None)
    if isinstance(row, dict) and int(row.get("sub_game", -1)) == sub_game:
        return row
    return None
