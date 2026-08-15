"""Human-play interactive CLI, decomposed from ``scripts/human_vs_rl.py``.

That filename remains the entry-point facade (CLI invocation by filename is
unchanged); these modules hold the implementation, one concern per file, each
within the 150-line rule.

The former ``agent_*`` siblings served a human-vs-agent CLI built on the legacy
``agent`` package. That package is gone, so those modules could no longer be
imported at all; they were removed rather than left as decoration.
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
