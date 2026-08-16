"""Live GUI web application — local-truth only, no hidden coordinates."""

import asyncio
import json

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from cop_worker.gui.live_view_model import LiveViewModel

# Global view model — set by production runtime via set_view_model()
_view_model: LiveViewModel | None = None


def set_view_model(vm: LiveViewModel) -> None:
    global _view_model, _ROLE
    _view_model = vm
    _ROLE = getattr(vm, "_role", "")


app = FastAPI(title="Cop vs Thief — Local Truth Live GUI")
_ROLE = ""  # set by set_view_model for the page header


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(_html_page())


@app.get("/api/view")
async def current_view() -> JSONResponse:
    if _view_model is None:
        return JSONResponse({"error": "no game active"}, status_code=503)
    update = _view_model.get_update()
    if update is None:
        return JSONResponse({"error": "no view available"}, status_code=503)
    return JSONResponse(json.loads(update.to_json()))


@app.get("/api/stream")
async def stream(request: Request) -> StreamingResponse:
    """SSE endpoint for real-time view updates."""

    async def event_generator():
        last_id = -1
        while True:
            if await request.is_disconnected():
                break
            if _view_model is not None:
                update = _view_model.get_update()
                if update and int(update.event_id) > last_id:
                    last_id = int(update.event_id)
                    yield f"data: {update.to_json()}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/replay", response_class=HTMLResponse)
async def replay_page() -> HTMLResponse:
    from cop_worker.gui.replay_page import REPLAY_PAGE

    return HTMLResponse(REPLAY_PAGE)


@app.get("/api/replay/logs")
async def replay_logs() -> JSONResponse:
    """Names of this repo's own reference-v3 logs (results/log_*.json)."""
    from pathlib import Path

    results = Path(__file__).resolve().parents[2] / "results"
    return JSONResponse(sorted(f.name for f in results.glob("log_*.json")))


@app.get("/api/replay/steps")
async def replay_steps(log: str) -> JSONResponse:
    """Per-step verdicts from the shared core; refuses paths outside results/."""
    from pathlib import Path

    from cop_worker.replay.ref3_steps import verify_file

    results = Path(__file__).resolve().parents[2] / "results"
    target = (results / Path(log).name).resolve()
    if not target.is_file() or target.parent != results.resolve():
        return JSONResponse({"error": "unknown log"}, status_code=404)
    from cop_worker.replay.ref3_steps import load_log
    from cop_worker.replay.replay_board import board_states

    overall, steps = verify_file(target)
    doc = load_log(target)
    boards = board_states(steps, our_role=(doc.get("summary") or {}).get("role", "police"))
    return JSONResponse(
        {
            "overall": overall,
            "steps": [
                {
                    "side": s.side,
                    "step": s.step,
                    "payload": s.payload,
                    "stored_commit": s.stored_commit,
                    "recomputed_commit": s.recomputed_commit,
                    "ok": s.ok,
                    "board": boards[i],
                }
                for i, s in enumerate(steps)
            ],
        }
    )


def _html_page() -> str:
    from cop_worker.gui.page import LIVE_PAGE

    return LIVE_PAGE
