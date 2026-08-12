"""In-process league series runner internals, decomposed from
``scripts/run_league_game.py``.

The original filename remains the entry point and public facade; these modules
hold the implementation within the 150-line rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add both repos to sys.path so cop_worker, thief_worker, league_manager are importable
_COP_REPO = Path(__file__).resolve().parents[2]  # vibecode-cop/
_THIEF_REPO = _COP_REPO.parent / "vibecode-thief"
for _p in (str(_COP_REPO), str(_THIEF_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
