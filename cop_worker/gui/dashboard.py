"""Persistent dashboard: game history + replays always, live panels when up.

Runs independently of any match (scripts/gui_dashboard.py, default port 8780)
and never participates in play - it only READS: result/log artifacts from
results/, and the per-role live GUIs' own /api/view when a match happens to be
running. Local truth is preserved by construction: each live panel is that
role's own filtered view, served by that role's worker; this process adds no
data of its own.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from cop_worker.gui import app as live_app

RESULTS = Path(__file__).resolve().parents[2] / "results"
LIVE_PORTS = {"cop": 8781, "thief": 8782}
OUR_GROUP = "vibecode"
#: Opponents that are local benches, not real teams (peer simulator, kit sparring).
SIM_GROUPS = {"peersim01", "sparring-match", "selftest"}

app = FastAPI(title="Cop/Thief — Dashboard")
# Replays are the same endpoints the in-match GUI serves; one implementation.
app.add_api_route("/replay", live_app.replay_page, response_class=HTMLResponse)
app.add_api_route("/api/replay/logs", live_app.replay_logs)
app.add_api_route("/api/replay/steps", live_app.replay_steps)


@app.get("/", response_class=HTMLResponse)
async def hub() -> HTMLResponse:
    from cop_worker.gui.hub_page import HUB_PAGE

    return HTMLResponse(HUB_PAGE)


def _counted_index() -> dict:
    """game_id -> ledger entry, from results/counted_series.json ({} if absent)."""
    try:
        ledger = json.loads((RESULTS / "counted_series.json").read_text(encoding="utf-8"))
        return {e.get("game_id"): e for e in ledger.get("series", [])}
    except (OSError, json.JSONDecodeError):
        return {}


@app.get("/api/hub/games")
async def games() -> JSONResponse:
    """Every series with a result artifact, newest first, categorized.

    counted  - filed in the league ledger (results/counted_series.json)
    local    - a bench opponent (peer simulator / kit sparring), not a real team
    friendly - everything else. NOTE: result artifacts are per game_id, so only
    the LATEST series against an opponent is listed here; earlier friendlies
    against the same opponent live in reports/ref3_matches/ match logs.
    """
    counted = _counted_index()
    out = []
    for res in sorted(RESULTS.glob("result_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            doc = json.loads(res.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        game_id = doc.get("game_id", res.stem.removeprefix("result_"))
        groups = doc.get("groups") or []
        opponent = next((g for g in groups if g != OUR_GROUP), "?")
        if game_id in counted:
            category = "counted"
        elif opponent in SIM_GROUPS:
            category = "local"
        else:
            category = "friendly"
        fr = doc.get("final_result", {})
        score = fr.get("total_score", {})
        out.append(
            {
                "game_id": game_id,
                "category": category,
                "group": OUR_GROUP,
                "opponent": opponent,
                "windows": len(doc.get("sub_games", [])),
                "score": " – ".join(f"{k} {v}" for k, v in score.items()),
                "winner": fr.get("winner_group"),
                "mutual_sha": (doc.get("mutual_agreement") or {}).get("sha256", ""),
                "confirmed": bool((doc.get("mutual_agreement") or {}).get("confirmed")),
                "report_id": (counted.get(game_id) or {}).get("report_message_id", ""),
                "logs": sorted(p.name for p in RESULTS.glob(f"log_{game_id}_g*.json")),
            }
        )
    return JSONResponse(out)


@app.get("/api/hub/live")
async def live_status() -> JSONResponse:
    """Probe the per-role live GUIs (up only while a match is running)."""
    import httpx

    out = {}
    for role, port in LIVE_PORTS.items():
        state: dict = {"up": False}
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                resp = await client.get(f"http://127.0.0.1:{port}/api/view")
            if resp.status_code == 200:
                view = resp.json().get("view", {})
                state = {
                    "up": True,
                    "sub_game": view.get("sub_game"),
                    "step": view.get("turn"),
                    "your_turn": view.get("your_turn"),
                }
        except Exception:
            pass  # not running - the normal idle state, never an error
        out[role] = state
    return JSONResponse(out)
