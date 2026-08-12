"""Shared paths, logger, and ref-v3 canonical game terms."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — add both repos so thief_worker is importable in-process
# ---------------------------------------------------------------------------
_COP_REPO = Path(__file__).resolve().parents[2]
if str(_COP_REPO) not in sys.path:
    sys.path.insert(0, str(_COP_REPO))

THIEF_REPO = _COP_REPO.parent / "vibecode-thief"
if THIEF_REPO.is_dir() and str(THIEF_REPO) not in sys.path:
    sys.path.insert(0, str(THIEF_REPO))

LOG_DIR = Path("D:/tmp/ref3_selfplay")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ref-v3 canonical game terms
# ---------------------------------------------------------------------------
TERMS: dict = {
    "board_size": 7,
    "smell_grid_size": 5,
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "max_steps": 35,
    "survival_threshold": 35,
    "barriers_max": 14,
    "num_games": 6,
}

# Role schedule: sub_game_number -> cop_worker role
ROLE_SCHEDULE: dict[int, str] = {
    1: "police",
    2: "thief",
    3: "police",
    4: "thief",
    5: "police",
    6: "thief",
}
