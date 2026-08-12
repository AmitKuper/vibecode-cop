"""Human-play interactive CLIs, decomposed from ``scripts/human_vs_agent.py``
and ``scripts/human_vs_rl.py``.

The original filenames remain the entry-point facades (CLI invocation by
filename is unchanged); these modules hold the implementation: one concern per
file, every file within the 150-line rule. ``agent_*`` modules serve the
human-vs-agent CLI; ``rl_*`` modules serve the human-vs-rl CLI. The two CLIs
deliberately keep separate copies of any function whose text differs — only
byte-identical code is shared (``keys``).
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
