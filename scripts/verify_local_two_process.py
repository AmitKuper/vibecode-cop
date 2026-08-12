#!/usr/bin/env python3
"""Run and independently verify the real clean-tree two-process counted series.

This file is the entry point and public FACADE; the implementation lives in
the ``verify_two_process`` package (one concern per module, ≤150 lines each):

    util            repo paths + process/hash helpers
    verify_ledgers  independent-ledger consensus + fake-Gmail checks
    verify          _verify_artifacts — signatures, audits, result consensus
    runner          run() — spawn thief + cop counted CLIs — and main()
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_REPO_ROOT), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from verify_two_process.runner import main, run
from verify_two_process.util import (
    COP_REPO,
    ROOT,
    THIEF_REPO,
    WORKSPACE,
    _contains_private_nonce_key,
    _free_port,
    _python,
    _sha256,
    _wait_for_listener,
)
from verify_two_process.verify import _verify_artifacts

__all__ = [
    "COP_REPO",
    "ROOT",
    "THIEF_REPO",
    "WORKSPACE",
    "_contains_private_nonce_key",
    "_free_port",
    "_python",
    "_sha256",
    "_verify_artifacts",
    "_wait_for_listener",
    "main",
    "run",
]

if __name__ == "__main__":
    raise SystemExit(main())
