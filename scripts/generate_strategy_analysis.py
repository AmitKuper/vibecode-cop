"""Generate executable strategy ablations for the exact release checkpoint.

This file is the entry point and public FACADE. The implementation lives in the
``strategy_analysis`` package: report (_load_network, _summary, _write_csv),
cli (main).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(REPO_ROOT), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from strategy_analysis.cli import main
from strategy_analysis.report import _load_network, _summary, _write_csv

__all__ = [
    "REPO_ROOT",
    "_load_network",
    "_summary",
    "_write_csv",
    "main",
]

if __name__ == "__main__":
    main()
