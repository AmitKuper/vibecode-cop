"""Persistent dashboard: game history + replays always, live panels when up.

Runs independently of any match (scripts/gui_dashboard.py, default port 8780)
and never participates in play - it only READS: result/log artifacts from
results/, the runtime config, and the per-role live GUIs' own /api/view when a
match happens to be running. Endpoints live in hub_api; this module wires the
app together.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from cop_worker.gui import app as live_app
from cop_worker.gui.hub_api import router

app = FastAPI(title="Cop/Thief — Dashboard")
app.include_router(router)
try:  # human-vs-model play exists only where the engine does (cop repo);
    from cop_worker.gui.play_api import router as play_router

    app.include_router(play_router)
except ImportError:  # the hub feature-detects via /api/play/available
    pass
# Replays are the same endpoints the in-match GUI serves; one implementation.
app.add_api_route("/replay", live_app.replay_page, response_class=HTMLResponse)
app.add_api_route("/api/replay/logs", live_app.replay_logs)
app.add_api_route("/api/replay/steps", live_app.replay_steps)


@app.get("/play", response_class=HTMLResponse)
async def play() -> HTMLResponse:
    from cop_worker.gui.play_page import PLAY_PAGE

    return HTMLResponse(PLAY_PAGE)


@app.get("/", response_class=HTMLResponse)
async def hub() -> HTMLResponse:
    from cop_worker.gui.hub_page import HUB_PAGE

    return HTMLResponse(HUB_PAGE)
