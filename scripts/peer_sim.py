#!/usr/bin/env python3
"""peersim01 — REALISTIC PEER SIMULATOR: a bench stand-in for real league peers.

Behaves like the peers we actually faced (najamjad / imreeyal / uoh-sqak), not
like the kit's gentle sparring client, so integration bugs surface on the bench:

* ONE FastMCP server on ONE port (default 9377) serves all six windows, its four
  reference-v3 tools advertising najamjad's SUPERSET schema (``message`` AND
  ``payload`` properties, object-typed, none required).
* Per window it opens a FRESH client session to the correct vibecode door, sends
  a LEAN najamjad-shaped greeting, plays real commit-reveal turns (thief-first,
  per-sender numbering, pre-decay 0.9-peak chebyshev scent, template hints),
  audits, sends a done control — then CLOSES the session cleanly, firing the
  streamable-http DELETE that once wedged our thief door.
* Quirks (on by default): eager next-window greeting to the currently-connected
  (often wrong) door ~2s in; duplicate greeting re-sends every ~5s while
  waiting; a 3-8s slow dial between windows.

Bench acceptance:
    uv run python scripts/peer_sim.py
    uv run python scripts/live_match_ref3.py --match --config peersim --no-email
    -> expect "[match] STATUS: audits 6/6 ok"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_REPO_ROOT), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from peer_sim_impl.runner import run_sim


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="peersim01 — realistic league-peer simulator")
    p.add_argument("--port", type=int, default=9377, help="single serving port (all windows)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument(
        "--config",
        default="peersim",
        help="config/opponents/<name>/ profile to read the vibecode door ports from",
    )
    p.add_argument("--windows", type=int, default=6)
    p.add_argument(
        "--cop-door-url",
        default=None,
        help="dial vibecode's COP door at this URL (e.g. an ngrok tunnel) instead of localhost",
    )
    p.add_argument(
        "--thief-door-url",
        default=None,
        help="dial vibecode's THIEF door at this URL (tunnel testing) instead of localhost",
    )
    p.add_argument(
        "--greeting-timeout",
        type=float,
        default=900.0,
        help="how long to wait for vibecode's greeting (first attempt per window)",
    )
    p.add_argument("--turn-timeout", type=float, default=180.0)
    p.add_argument(
        "--no-eager-greeting",
        action="store_true",
        help="disable quirk (a): early next-window greeting to the current door",
    )
    p.add_argument(
        "--no-duplicate-greeting",
        action="store_true",
        help="disable quirk (b): ~5s duplicate greeting re-sends while waiting",
    )
    p.add_argument(
        "--no-slow-dial",
        action="store_true",
        help="disable quirk (c): 3-8s wait before dialing each window",
    )
    return p


def main() -> int:
    args = _build_parser().parse_args()
    return asyncio.run(run_sim(args))


if __name__ == "__main__":
    sys.exit(main())
