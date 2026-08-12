"""Head-to-head arena harnesses, decomposed from scripts/arena_search_eval.py
and scripts/arena_belief_eval.py.

The two original filenames remain the entry points and public facades
(``arena_archetypes.py`` and ``render_match_visuals.py`` import through them).
These modules hold the implementation: one concern per file, every file within
the 150-line rule.

    search_impl    N, CheckpointPolicy, make_policy, _obs (chebyshev frame)
    search_play    play -- the chebyshev-physics round loop
    search_cli     main for arena_search_eval
    belief_impl    _RecurrentThief, _load_thief, _book_field (book frame)
    belief_play    N, play -- the book-physics round loop
    belief_cli     main for arena_belief_eval
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _SCRIPTS_DIR.parent
# Importable however we're launched: repo root (cop_worker) + scripts dir (facades).
for _p in (str(_REPO_ROOT), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
