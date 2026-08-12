#!/usr/bin/env python3
"""Build the four league artifact kinds (config, log, declaration, result).

Schemas mirror anrbj666's shipped files (ARTIFACT_FORMATS.md). All four are written
to the repo per game; ONLY the result (final_game_result) is emailed — body = its
canonical bytes, one attachment = the same bytes under result_<game_id>.json.

This file is the public FACADE: scripts/ref3_match/* and cop_worker/sdk.py import
it by name. The implementation lives in the ``league_artifacts`` package (one
concern per module, ≤150 lines each):

    core         constants (OUR_REPOS, OUR_MCP), canonical _sha, constitution
                 access (load_constitution, config_sha256), now_iso, write_artifact
    scoring      score_series — Appendix-F rows + final_result aggregate
    builders     build_config, build_log
    declaration  _hardware_spec, build_declaration
    result       mutual_agreement_sha, build_result
    report       update_counted_ledger, email_result
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent
for _p in (str(_REPO_ROOT), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from league_artifacts.builders import build_config, build_log
from league_artifacts.core import (
    GAME_JSON_PATH,
    OUR_MCP,
    OUR_REPOS,
    REPO_ROOT,
    _sha,
    config_sha256,
    load_constitution,
    now_iso,
    write_artifact,
)
from league_artifacts.declaration import _hardware_spec, build_declaration
from league_artifacts.report import email_result, update_counted_ledger
from league_artifacts.result import build_result, mutual_agreement_sha
from league_artifacts.scoring import score_series

__all__ = [
    "GAME_JSON_PATH",
    "OUR_MCP",
    "OUR_REPOS",
    "REPO_ROOT",
    "_hardware_spec",
    "_sha",
    "build_config",
    "build_declaration",
    "build_log",
    "build_result",
    "config_sha256",
    "email_result",
    "load_constitution",
    "mutual_agreement_sha",
    "now_iso",
    "score_series",
    "update_counted_ledger",
    "write_artifact",
]
