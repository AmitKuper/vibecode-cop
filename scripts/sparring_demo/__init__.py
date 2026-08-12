"""Demo cop-vs-sparring-kit runtime, decomposed from scripts/demo_vs_sparring.py.

``scripts/demo_vs_sparring.py`` remains the entry point and public facade.
These modules hold the implementation: one concern per file, every file within
the 150-line rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _SCRIPTS_DIR.parent
# Importable however we're launched: repo root (cop_worker) + scripts dir.
for _p in (str(_REPO_ROOT), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

REPO_ROOT = _REPO_ROOT
KIT_ROOT = REPO_ROOT.parent / "external" / "copthief-league-protocol"
