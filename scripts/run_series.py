#!/usr/bin/env python3
"""Run a six-gamelet P2P series via PeerRuntime (cop drives, thief responds).

The cop PeerRuntime drives each gamelet by calling the thief's MCP directly —
no central coordinator is involved.

Prerequisites:
  1. Start the thief agent:  python -m thief thief/config.toml
  2. Run this script from the cop repo root:

     python scripts/run_series.py --thief-url http://localhost:5001/mcp

Optional arguments:
  --thief-url     Thief's MCP endpoint  (default: http://localhost:5001/mcp)
  --secret        Shared HMAC secret    (default: dev-secret-change-me)
  --games-dir     Directory for output  (default: cop/games)
  --n-gamelets    Number of gamelets    (default: 6)
  --config        Path to config.toml   (default: cop/config.toml or config.toml)

This file is the entry point and public FACADE; the implementation lives in the
``series_run`` package (one concern per module, ≤150 lines each):

    legacy_stubs        sentinels for modules deleted in the Phase 1 restructure
    tokens              _TOKEN_KEYS + _validated_token_totals
    core                run_series (validation + the unconditional raise)
    legacy_gamelets     unreachable original gamelet loop, kept for reference
    legacy_exchange     unreachable original result exchange, kept for reference
    cli                 _parse_args, _load_config, main
"""

import asyncio
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_REPO_ROOT), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from series_run.cli import _load_config, _parse_args, main
from series_run.core import run_series
from series_run.legacy_stubs import (
    PeerRuntime,
    ResultExchangeError,
    _RemovedModule,
    exchange_series_result,
    gamelet_from_game_id,
    get_coordinator,
)
from series_run.tokens import _TOKEN_KEYS, _validated_token_totals

logger = logging.getLogger(__name__)

__all__ = [
    "PeerRuntime",
    "ResultExchangeError",
    "_RemovedModule",
    "_TOKEN_KEYS",
    "_load_config",
    "_parse_args",
    "_validated_token_totals",
    "exchange_series_result",
    "gamelet_from_game_id",
    "get_coordinator",
    "logger",
    "main",
    "run_series",
]

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
