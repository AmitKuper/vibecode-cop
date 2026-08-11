"""Reference-v3 live-match runtime, decomposed from scripts/live_match_ref3.py.

``scripts/live_match_ref3.py`` remains the single entry point and public facade
(the SDK spawns it by filename; tests import through it). These modules hold the
implementation: one concern per file, every file within the 150-line rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _SCRIPTS_DIR.parent
# Importable however we're launched: repo root (cop_worker) + scripts dir (ref3_artifacts).
for _p in (str(_REPO_ROOT), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
