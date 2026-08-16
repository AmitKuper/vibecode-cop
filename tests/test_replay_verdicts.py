"""Replay verification core + both pages carry the book's mandatory verdicts."""

from __future__ import annotations

from cop_worker.gui.page import LIVE_PAGE
from cop_worker.gui.replay_page import REPLAY_PAGE
from cop_worker.protocol.reference_v3.hashing import reference_commit
from cop_worker.replay import ref3_steps


def _synthetic_log(tamper: bool = False) -> dict:
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
    if tamper:
        records[1]["payload"]["move"] = "S"  # payload changed AFTER sealing
    return {"records": records, "opponent_records": []}


def test_pristine_log_is_verified_ok():
    steps = ref3_steps.iter_steps(_synthetic_log())
    assert ref3_steps.overall_verdict(steps) == ref3_steps.VERIFIED
    assert all(s.ok for s in steps)


def test_one_tampered_step_poisons_the_whole_match():
    steps = ref3_steps.iter_steps(_synthetic_log(tamper=True))
    assert ref3_steps.overall_verdict(steps) == ref3_steps.TAMPERED
    assert [s.step for s in steps if not s.ok] == [2]  # pinpointed, not just failed


def test_missing_nonce_is_unverifiable_not_verified():
    doc = _synthetic_log()
    del doc["records"][0]["nonce"]
    steps = ref3_steps.iter_steps(doc)
    assert ref3_steps.overall_verdict(steps) == ref3_steps.TAMPERED


# --- pages carry the book's mandatory elements ------------------------------


def test_live_page_has_the_mandatory_panels():
    for marker in ("YOUR TURN", "LOCKED", "belief", "scent", "may lie", "audits"):
        assert marker in LIVE_PAGE, marker


def test_replay_page_shows_both_verdicts():
    for marker in ("Verified OK", "TAMPERED", "recomputed", "slider"):
        assert marker in REPLAY_PAGE, marker


def test_dashboard_games_endpoint_lists_real_series():
    """The hub's history table is built from the results tree, newest first."""
    import asyncio
    import json as _json

    from cop_worker.gui.dashboard import games

    payload = _json.loads(asyncio.run(games()).body)
    assert payload, "results/ holds series but the dashboard listed none"
    row = payload[0]
    assert {"game_id", "windows", "score", "winner", "mutual_sha", "logs"} <= set(row)


def test_dashboard_hub_page_has_the_three_surfaces():
    from cop_worker.gui.hub_page import HUB_PAGE

    for marker in ("COP live view", "THIEF live view", "Replay viewer", "Game history"):
        assert marker in HUB_PAGE, marker
