"""Launcher for one reference-v3 role-worker process (cop OR thief).

Spawned by the split-architecture orchestrator; see ref3_match/role_worker.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ref3_match.role_worker import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
