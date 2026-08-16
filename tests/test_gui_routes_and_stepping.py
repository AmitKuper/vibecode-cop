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

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from cop_worker.gui import app as live_gui  # noqa: E402
from cop_worker.gui.dashboard import app as dashboard_app  # noqa: E402
from cop_worker.protocol.reference_v3.hashing import reference_commit  # noqa: E402

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
        assert row["category"] in {"counted", "friendly", "local"}


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
    # per side, protocol steps are non-decreasing: index i+1 is "the next record"
    for side in ("ours", "opponent"):
        seq = [s["step"] for s in steps if s["side"] == side]
        assert seq == sorted(seq), f"{side} records are not in protocol order"
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


def _write_synthetic_log(tmp_path: Path) -> Path:
    records = []
    for step in (1, 2, 3):
        payload = {
            "step": step,
            "role": "thief",
            "sub_game": 1,
            "position": [3, 3],
            "move": "N",
            "intent": "truth",
        }
        nonce = f"nonce{step:02d}"
        records.append(
            {"payload": payload, "nonce": nonce, "commit": reference_commit(payload, nonce)}
        )
    log = tmp_path / "log_synthetic_g01.json"
    log.write_text(json.dumps({"records": records, "opponent_records": []}), encoding="utf-8")
    return log


def test_cli_stepper_moves_next_prev_jump(tmp_path, monkeypatch):
    from replay_stepper import interactive

    log = _write_synthetic_log(tmp_path)
    keys = iter(["n", "n", "p", "j 1", "q"])
    monkeypatch.setattr("builtins.input", lambda *_: next(keys))
    out = io.StringIO()
    with redirect_stdout(out):
        code = interactive(str(log))
    text = out.getvalue()
    # forward, forward, back, jump: every position was rendered
    for pos in ("timeline 1/3", "timeline 2/3", "timeline 3/3"):
        assert pos in text, pos
    assert text.count("timeline 2/3") >= 2, "prev must re-render position 2"
    assert "final verdict: Verified OK" in text
    assert code == 0


def test_cli_stepper_clamps_at_both_ends(tmp_path, monkeypatch):
    from replay_stepper import interactive

    log = _write_synthetic_log(tmp_path)
    keys = iter(["p", "n", "n", "n", "q"])  # p at start, n past the end
    monkeypatch.setattr("builtins.input", lambda *_: next(keys))
    out = io.StringIO()
    with redirect_stdout(out):
        interactive(str(log))
    text = out.getvalue()
    assert "timeline 0/3" not in text, "prev at the start must clamp, not underflow"
    assert "timeline 4/3" not in text, "next at the end must clamp, not overflow"
