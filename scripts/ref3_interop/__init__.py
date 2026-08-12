"""Reference-v3 interop verifier internals, decomposed from
``scripts/verify_reference_v3_interop.py``.

The original filename remains the entry point and public facade; these modules
hold the implementation within the 150-line rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _SCRIPTS_DIR.parent
# Importable however we're launched: repo root (agent/cop_worker) + scripts dir.
for _p in (str(_REPO_ROOT), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
