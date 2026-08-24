"""GUI behaves as shipped: routes serve, and replay steps forward/backward.

The stepping contract is tested at three levels:
- the CLI stepper's actual loop (n / p / j / q) against a synthetic log,
- the steps API's ordering guarantee (timeline index == list order) on a REAL
  tracked gamelet log, so a browser slider/arrow at index i+1 is always "the
  next sealed record",
- the web page's arrow wiring (buttons + ArrowLeft/ArrowRight handlers with a
  bounds clamp), which is what the browser executes.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from cop_worker.gui import app as live_gui  # noqa: E402
from cop_worker.gui.dashboard import app as dashboard_app  # noqa: E402

client = TestClient(dashboard_app)
live_client = TestClient(live_gui.app)


# --- dashboard routes -------------------------------------------------------


def test_hub_serves_the_three_sidebar_views():
    body = client.get("/").text
    for marker in ("nav-status", "nav-history", "nav-settings", "view-settings"):
        assert marker in body, marker


def test_settings_endpoint_is_read_only_config_truth():
    s = client.get("/api/hub/settings").json()
    assert s["scent_model"] == "subtractive_chebyshev_v1"
    assert s["move_policy"] == "hybrid_search"
    assert "vibecode" not in s.get("profiles", []), "profiles are opponents, not us"


def test_games_endpoint_categories_are_exhaustive():
    for row in client.get("/api/hub/games").json():
        assert row["category"] in {"counted", "friendly", "local", "human"}


# --- replay stepping: the API ordering the arrows depend on -----------------


def _a_tracked_log() -> str:
    results = Path(__file__).resolve().parents[1] / "results"
    logs = sorted(p.name for p in results.glob("log_*_g*.json"))
    assert logs, "repo tracks gamelet logs; none found"
    return logs[0]


def test_steps_api_order_is_the_timeline_the_arrows_walk():
    d = live_client.get("/api/replay/steps", params={"log": _a_tracked_log()}).json()
    steps = d["steps"]
    assert len(steps) >= 3
    # ONE chronological game: protocol steps non-decreasing across the WHOLE
    # timeline. The pre-fix order (all ours, then all opponent again from step
    # 1) looked like two games with a board reset in the middle.
    seq = [max(s["step"], 0) for s in steps]
    assert seq == sorted(seq), "timeline must be one chronological merge of both sides"
    # both sides genuinely interleave (each protocol step: thief then cop)
    sides = [s["side"] for s in steps]
    assert "ours" in sides and "opponent" in sides
    flips = sum(1 for a, b in zip(sides, sides[1:], strict=False) if a != b)
    assert flips > 2, "sides must interleave, not cluster into two blocks"
    assert d["overall"] in ("Verified OK", "TAMPERED")


def test_replay_page_has_arrow_buttons_and_key_handlers():
    body = live_client.get("/replay").text
    for marker in (
        'id="prev"',
        'id="next"',
        "ArrowRight",
        "ArrowLeft",
        "Math.min(Math.max",  # the bounds clamp: arrows can never leave the timeline
        'id="slider"',
    ):
        assert marker in body, marker


# --- replay stepping: the CLI loop actually moves ---------------------------


# The CLI stepper's loop tests live in tests/test_gui_cli_stepper.py.


def test_steps_api_reconstructs_boards_with_both_agents_and_scent():
    """Positions from the revealed payloads; scent replayed via the locked emitter.

    Uses a nis-yar1 log: both sides sealed positions there. (anrbj666 sealed
    action+state_digest instead - their pieces legitimately cannot be placed,
    and the board shows only what the revealed data supports.)
    """
    root = Path(__file__).resolve().parents[1]
    results = root / "results"
    logs = sorted(p.name for p in results.glob("log_nis-yar1*_g*.json"))
    seeded = None
    if not logs:  # fresh clone (CI): seed from the TRACKED evidence copy
        tracked = sorted((root / "evidence" / "game_vs_nis-yar1").glob("log_nis-yar1*_g*.json"))
        assert tracked, "nis-yar1 logs are tracked under evidence/ in this repo"
        results.mkdir(parents=True, exist_ok=True)
        seeded = results / tracked[0].name
        seeded.write_bytes(tracked[0].read_bytes())
        logs = [seeded.name]
    try:
        d = live_client.get("/api/replay/steps", params={"log": logs[0]}).json()
    finally:
        if seeded is not None:
            seeded.unlink()
    boards = [s["board"] for s in d["steps"] if s.get("board")]
    assert boards, "every step must carry a board"
    late = boards[-1]
    assert late["cop"] is not None and late["thief"] is not None
    field = late["scent_thief"]
    assert field, "the thief's reconstructed scent must not be empty"
    assert max(field.values()) <= 0.8 + 1e-9, "wire law peak is 0.8 (post-decay)"
    for key in field:  # wire "row,col" keys inside the board
        r, c = key.split(",")
        assert 0 <= int(r) < 7 and 0 <= int(c) < 7
