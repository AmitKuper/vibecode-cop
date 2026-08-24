"""Stray-greeting routing for role workers (split from role_worker)."""

from __future__ import annotations


def _drain_strays(session, *, beyond: int = 0) -> list[dict]:
    """Remove and return greetings for sub-games beyond `beyond` from our inbox.

    A single-URL peer (kit sparring; a single-service opponent) can deliver the
    NEXT window's Step-0 greeting to whichever of our endpoints it last dialed.
    Greetings are the opponent's public broadcast — relaying them through the
    orchestrator to the right role worker is routing, not shared role state.
    """
    strays, keep = [], []
    for msg in list(session.agreements):
        n = msg.get("sub_game_number")
        (strays if isinstance(n, int) and n > beyond else keep).append(msg)
    session.agreements.clear()
    session.agreements.extend(keep)
    return strays
