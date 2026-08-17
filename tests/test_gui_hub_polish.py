"""GUI polish round 2 (user review): play keys, history labels, live board,
replay picker/attribution, and dead-reckoned opponents for position-less dialects."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from cop_worker.gui import app as live_gui
from cop_worker.gui.hub_page import HUB_PAGE
from cop_worker.gui.play_page import PLAY_PAGE
from cop_worker.gui.replay_page import REPLAY_PAGE
from cop_worker.protocol.reference_v3.hashing import reference_commit
from cop_worker.replay.ref3_steps import chronological, iter_steps
from cop_worker.replay.replay_board import _move_label, board_states

live_client = TestClient(live_gui.app)
RESULTS = Path(__file__).resolve().parents[1] / "results"


def _sealed(payload: dict, nonce: str) -> dict:
    return {"payload": payload, "nonce": nonce, "commit": reference_commit(payload, nonce)}


def test_play_page_binds_letter_keys_and_shift_barriers():
    """N/S/E/W keys must move; Shift+direction must place a barrier (cop only)."""
    for marker in ("N:'N'", "S:'S'", "W:'W'", "E:'E'", "ArrowUp:'N'"):
        assert marker in PLAY_PAGE, marker
    assert "e.shiftKey" in PLAY_PAGE and "'PLACE_'+dir" in PLAY_PAGE
    assert "Shift+key" in PLAY_PAGE  # the barrier fieldset says how


def test_history_rotated_label_explains_itself():
    assert "<i>rotated</i>" not in HUB_PAGE
    assert "no replay (logs rotated)" in HUB_PAGE
    assert "overwrote" in HUB_PAGE  # tooltip says WHY there is no link


def test_hub_status_renders_a_native_live_board():
    """Status shows a real board (own pos + belief + scent) — not an iframe that
    only works when the browser can reach 127.0.0.1 directly."""
    for marker in ("liveBoard", "belief_heatmap", "opponent_scent", "own_position"):
        assert marker in HUB_PAGE, marker
    assert '<iframe src="http' not in HUB_PAGE, "no cross-port iframes on Status"


def test_hub_hands_keyboard_focus_to_the_embedded_frame():
    assert "contentWindow.focus()" in HUB_PAGE


def test_replay_picker_replaces_the_select():
    assert "<select" not in REPLAY_PAGE
    assert 'id="picker"' in REPLAY_PAGE and 'class="pk"' in REPLAY_PAGE


def test_replay_names_the_group_behind_each_role():
    assert 'id="who"' in REPLAY_PAGE
    assert "opponent_group_id" in REPLAY_PAGE
    assert "COP" in REPLAY_PAGE and "THIEF" in REPLAY_PAGE


def test_move_label_understands_every_dialect():
    assert _move_label({"move": "S"}) == "S"
    assert _move_label({"move": "MOVE:E"}) == "E"
    assert _move_label({"action": {"type": "move", "move": "N"}}) == "N"
    for stay in ("HOLD:-", "PLACE_E", "BARRIER:E", "barrier:3,4"):
        assert _move_label({"move": stay}) == "STAY", stay
    assert _move_label({"move": "confirm_capture"}) is None
    assert _move_label({}) is None


def _move_only_doc() -> dict:
    ours = [
        _sealed(
            {"step": n, "role": "thief", "sub_game": 1, "position": [3, 3 + n], "move": "S"},
            f"nt{n:02d}",
        )
        for n in (1, 2, 3)
    ]
    # anrbj666-shaped opponent: sealed moves, no positions. N is wall-clamped
    # at the (0,0) start; W is wall-clamped after S.
    theirs = [
        _sealed(
            {"step": n, "role": "police", "action": {"type": "move", "move": m}},
            f"np{n:02d}",
        )
        for n, m in ((1, "N"), (2, "S"), (3, "W"))
    ]
    return {"records": ours, "opponent_records": theirs, "summary": {"role": "thief"}}


def test_board_states_dead_reckons_a_move_only_opponent():
    doc = _move_only_doc()
    steps = chronological(iter_steps(doc), "thief")
    boards = board_states(steps, our_role="thief")
    last = boards[-1]
    assert last["thief"] == [3, 6], "sealed positions stay authoritative"
    assert last["cop"] == [0, 1], "N clamped at the corner, S applied, W clamped"
    assert last["reckoned"] == ["cop"], "viewers must see WHICH path is reconstructed"
    assert last["scent_cop"], "a reconstructed path still emits scent"
    assert boards[0]["reckoned"] == ["cop"]


def test_steps_api_reports_summary_and_reckoned_boards():
    seeded = RESULTS / "log_test-reckon_g01.json"
    doc = _move_only_doc()
    doc["summary"] = {"role": "thief", "group_id": "vibecode", "opponent_group_id": "anrbj666"}
    seeded.write_text(json.dumps(doc), encoding="utf-8")
    try:
        d = live_client.get("/api/replay/steps", params={"log": seeded.name}).json()
        assert d["overall"] == "Verified OK"
        assert d["summary"]["group_id"] == "vibecode"
        assert d["summary"]["opponent_group_id"] == "anrbj666"
        assert d["summary"]["role"] == "thief"
        boards = [s["board"] for s in d["steps"]]
        assert boards[-1]["cop"] == [0, 1] and boards[-1]["reckoned"] == ["cop"]
    finally:
        seeded.unlink()
