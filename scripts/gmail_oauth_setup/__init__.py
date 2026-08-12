"""Gmail OAuth setup internals, decomposed from ``scripts/setup_gmail_oauth.py``.

The original filename remains the entry point and public facade; ``steps``
holds the implementation within the 150-line rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _SCRIPTS_DIR.parent
for _p in (str(_REPO_ROOT), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
