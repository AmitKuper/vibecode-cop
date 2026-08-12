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

This file is the entry point and public FACADE; the implementation lives in
the ``sparring_demo`` package (one concern per module, ≤150 lines each):

    netutil     port checks, subprocess stop, inbox polling
    game_loop   the cop-side reference-v3 sub-game loop
    runner      server/sparring lifecycle around the game loop
    cli         argument parsing + result summary
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_REPO_ROOT), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sparring_demo import KIT_ROOT, REPO_ROOT
from sparring_demo.cli import main
from sparring_demo.game_loop import _game_loop
from sparring_demo.netutil import (
    _check_port,
    _poll_deque,
    _poll_inbox_step,
    _stop,
    _wait_port_async,
)
from sparring_demo.runner import _run_all

__all__ = [
    "KIT_ROOT",
    "REPO_ROOT",
    "_check_port",
    "_game_loop",
    "_poll_deque",
    "_poll_inbox_step",
    "_run_all",
    "_stop",
    "_wait_port_async",
    "main",
]

if __name__ == "__main__":
    sys.exit(main())
