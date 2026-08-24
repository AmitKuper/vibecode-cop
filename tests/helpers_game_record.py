"""Shared fixture builders for the game-record tests (split, 150-line rule)."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ref3_match.game_record import build_game_record  # noqa: E402

from cop_worker.gui import app as live_gui  # noqa: E402

live_client = TestClient(live_gui.app)
RESULTS = Path(__file__).resolve().parents[1] / "results"


def _row() -> dict:
    """A settled sub-game row: we are the thief; the peer cop reveals at audit."""
    sent = [
        {
            "step": s,
            "sender": "thief",
            "commit": f"aa{s:02d}",
            "hint": f"going north {s}",
            "smell_grid": {"3,3": 0.8, "3,4": 0.5},
        }
        for s in (1, 2)
    ]
    received = [
        {
            "step": s,
            "sender": "police",
            "commit": f"bb{s:02d}",
            "hint": "you cannot hide",
            "smell_grid": {"0,0": 0.8},
            "barrier_placed": [1, 1] if s == 2 else None,
        }
        for s in (1, 2)
    ]
    ours = [
        {
            "commit": f"aa{s:02d}",
            "nonce": "n",
            "payload": {"step": s, "position": [3, 3 - s], "move": "N", "intent": "truth"},
        }
        for s in (1, 2)
    ]
    theirs = [
        {
            "commit": f"bb{s:02d}",
            "nonce": "m",
            "payload": {"step": s, "position": [0, s], "move": "S"},
        }
        for s in (1, 2)
    ]
    return {
        "wire_turns": {"sent": sent, "received": received},
        "our_records": ours,
        "opp_records": theirs,
        "summary": {"outcome": "survival", "audit": "Verified OK"},
    }


def _record() -> dict:
    return build_game_record("a-vs-b", "uid", 1, "thief", "peer", _row())
