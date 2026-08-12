"""League artifact builders, decomposed from scripts/ref3_artifacts.py.

``scripts/ref3_artifacts.py`` remains the public facade (scripts/ref3_match/*
and cop_worker/sdk.py import it by name). These modules hold the implementation:
one concern per file, every file within the 150-line rule.
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
