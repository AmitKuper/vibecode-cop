"""Human-vs-model play: the opponent is the real counted engine.

The strength check that matters: a thief that never moves must be captured on
the Manhattan-optimal schedule - the engine plays production search, not a toy.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from cop_worker.gui.dashboard import app

client = TestClient(app)


def test_play_is_available_and_feature_detectable():
    r = client.get("/api/play/available")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_production_cop_captures_a_frozen_thief_optimally():
    g = client.post("/api/play/new", json={"role": "thief", "budget": 1.0}).json()
    assert g["cop"] == [0, 0] and g["thief"] == [3, 3]
    moves = 0
    while not g["over"] and moves < 10:
        g = client.post("/api/play/move", json={"game": g["id"], "action": "STAY"}).json()
        moves += 1
    assert g["over"] and g["outcome"] == "capture"
    assert g["step"] <= 7, "distance 6 must fall in ~6 steps - anything slower is not our engine"


def test_illegal_moves_are_rejected_not_absorbed():
    g = client.post("/api/play/new", json={"role": "thief", "budget": 1.0}).json()
    assert client.post("/api/play/move", json={"game": g["id"], "action": "XX"}).status_code == 400
    assert client.post("/api/play/move", json={"game": "nope", "action": "N"}).status_code == 404


def test_human_cop_gets_model_thief_opening_and_can_place_barriers():
    g = client.post("/api/play/new", json={"role": "cop", "budget": 1.0}).json()
    assert g["last_model_action"], "thief moves first: the model must open"
    g2 = client.post("/api/play/move", json={"game": g["id"], "action": "PLACE_E"}).json()
    assert g2["barriers_left"] == 13 and [1, 0] in g2["barriers"]


def test_the_gui_cop_walls_an_evading_thief():
    # The GUI cop is the committed-hunt chain (operator playbook): against a
    # thief that keeps its distance it must start walling, not chase forever.
    deltas = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0), "STAY": (0, 0)}
    g = client.post("/api/play/new", json={"role": "thief", "budget": 1.0}).json()
    for _ in range(24):
        if g["over"] or g["barriers"]:
            break
        cop, me = g["cop"], g["thief"]
        best = None
        for a, (dx, dy) in deltas.items():
            q = [me[0] + dx, me[1] + dy]
            if not (0 <= q[0] < 7 and 0 <= q[1] < 7) or q in g["barriers"] or q == cop:
                continue
            d = abs(q[0] - cop[0]) + abs(q[1] - cop[1])
            if best is None or d > best[0]:
                best = (d, a)
        r = client.post("/api/play/move", json={"game": g["id"], "action": best[1]})
        if r.status_code != 200:
            break
        g = r.json()
    assert g["barriers"] or g["outcome"] == "capture", "hunt cop neither walled nor captured"


def test_scent_fields_flow_during_play():
    g = client.post("/api/play/new", json={"role": "thief", "budget": 1.0}).json()
    g = client.post("/api/play/move", json={"game": g["id"], "action": "N"}).json()
    assert g["scent_thief"], "our own trail must emit"
    assert g["scent_cop"], "the model's trail must emit"
    assert max(g["scent_cop"].values()) <= 0.8 + 1e-9  # wire-law peak
