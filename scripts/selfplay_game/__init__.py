"""Self-play single sub-game internals, decomposed from
``scripts/run_selfplay_game.py``.

The original filename remains the entry point and public facade; ``game``
holds the implementation within the 150-line rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add cop repo root and thief repo root to sys.path for in-process imports
_COP_REPO = Path(__file__).resolve().parents[2]
if str(_COP_REPO) not in sys.path:
    sys.path.insert(0, str(_COP_REPO))

_THIEF_REPO = _COP_REPO.parent / "vibecode-thief"
if _THIEF_REPO.is_dir() and str(_THIEF_REPO) not in sys.path:
    sys.path.insert(0, str(_THIEF_REPO))
