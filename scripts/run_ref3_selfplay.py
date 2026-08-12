"""Run a real ref-v3 self-play game over HTTP MCP transport (in-process variant).

Side A (cop_worker) plays as "police".
Side B (thief_worker) plays as "thief".
They exchange moves formatted strictly in ref-v3 wire format.

Real HTTP transport (FastMCP streamable-http) is probed first; if the endpoint
is unreachable, the game loop falls back to direct in-process calls with the
same ref-v3 message format, proving the protocol logic.

Usage:
    uv run python scripts/run_ref3_selfplay.py --sub-games 6 --max-steps 5

This file is the single entry point and public FACADE. The implementation
lives in the ``ref3_selfplay`` package (one concern per module, ≤150 lines):

    runtime     paths (THIEF_REPO, LOG_DIR), logger, TERMS, ROLE_SCHEDULE
    session     _MCPSession — streamable-http handshake + tool calls
    transport   _call_tool_http session routing, _probe_http, _try_real_http_probe
    inprocess   _ip_* direct-call wrappers in ref-v3 wire format
    subgame     run_one_subgame — commit-reveal exchange for one sub-game
    series      _run_subgames — the sub-game loop with JSONL + lifecycle events
    main        argument parsing, transport probe, series result emission
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_REPO_ROOT), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ref3_selfplay.inprocess import (
    _ip_deliver_commit,
    _ip_shutdown,
    _ip_start_gamelet,
    _ip_start_playing,
)
from ref3_selfplay.main import main
from ref3_selfplay.runtime import (
    _COP_REPO,
    LOG_DIR,
    ROLE_SCHEDULE,
    TERMS,
    THIEF_REPO,
    logger,
)
from ref3_selfplay.series import _run_subgames
from ref3_selfplay.session import _MCPSession
from ref3_selfplay.subgame import run_one_subgame
from ref3_selfplay.transport import (
    _call_tool_http,
    _cop_session,
    _probe_http,
    _thief_session,
    _try_real_http_probe,
)

__all__ = [
    "LOG_DIR",
    "ROLE_SCHEDULE",
    "TERMS",
    "THIEF_REPO",
    "_COP_REPO",
    "_MCPSession",
    "_call_tool_http",
    "_cop_session",
    "_ip_deliver_commit",
    "_ip_shutdown",
    "_ip_start_gamelet",
    "_ip_start_playing",
    "_probe_http",
    "_run_subgames",
    "_thief_session",
    "_try_real_http_probe",
    "logger",
    "main",
    "run_one_subgame",
]

if __name__ == "__main__":
    raise SystemExit(main())
