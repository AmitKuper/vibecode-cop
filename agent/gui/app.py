"""Live GUI web application — local-truth only, no hidden coordinates."""

import asyncio
import json

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from agent.gui.live_view_model import LiveViewModel

# Global view model — set by production runtime via set_view_model()
_view_model: LiveViewModel | None = None


def set_view_model(vm: LiveViewModel) -> None:
    global _view_model
    _view_model = vm


app = FastAPI(title="Cop vs Thief — Local Truth Live GUI")


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


def _html_page() -> str:
    return """<!DOCTYPE html>
<html>
<head><title>Live Game View</title>
<style>
body{font-family:monospace;background:#1a1a2e;color:#e0e0e0;margin:20px}
#banner{font-size:2em;font-weight:bold;padding:10px;border-radius:5px;margin-bottom:10px}
.your-turn{background:#1a5f3f;color:#00ff88}
.locked{background:#5f1a1a;color:#ff4444}
#grid{display:inline-block;margin:10px}
.cell{width:40px;height:40px;display:inline-block;text-align:center;line-height:40px;border:1px solid #333;font-size:16px}
.own{background:#2244aa}
.barrier{background:#555;color:#888}
.belief-low{background:#1a1a3a}
.belief-mid{background:#1a3a5a}
.belief-high{background:#1a5a8a}
.belief-max{background:#1a8aff}
#info{margin-top:10px;padding:10px;background:#222;border-radius:5px}
#hint{font-style:italic;color:#aaaaff}
</style></head>
<body>
<h1>Local Truth Live View</h1>
<div id="banner" class="locked">CONNECTING...</div>
<div id="grid"></div>
<div id="info">
  <div>Turn: <span id="turn">-</span> | Gamelet: <span id="gamelet">-</span></div>
  <div>Score: Cop <span id="cop-score">0</span> — Thief <span id="thief-score">0</span></div>
  <div>Barriers remaining: <span id="barriers">-</span></div>
  <div>Protocol state: <span id="proto-state">-</span></div>
  <div>Hint: <span id="hint">-</span> (reliability: <span id="hint-rel">-</span>)</div>
</div>
<script>
const es = new EventSource('/api/stream');
es.onmessage = e => {
  const data = JSON.parse(e.data);
  const view = data.view;
  const banner = document.getElementById('banner');
  if (view.your_turn) { banner.textContent='YOUR TURN'; banner.className='your-turn'; }
  else { banner.textContent='LOCKED — Waiting for opponent'; banner.className='locked'; }
  document.getElementById('turn').textContent = view.turn;
  document.getElementById('gamelet').textContent = view.gamelet;
  document.getElementById('cop-score').textContent = (view.score||{}).cop||0;
  document.getElementById('thief-score').textContent = (view.score||{}).thief||0;
  document.getElementById('barriers').textContent = view.own_barriers_remaining;
  document.getElementById('proto-state').textContent = view.protocol_state;
  document.getElementById('hint').textContent = view.last_hint || '(none)';
  document.getElementById('hint-rel').textContent = (view.hint_reliability||0).toFixed(2);
  renderGrid(view);
};
function renderGrid(view) {
  const n = view.belief_heatmap ? view.belief_heatmap.length : 7;
  const grid = document.getElementById('grid');
  let html = '';
  const belief = view.belief_heatmap || [];
  for (let r=0;r<n;r++) {
    for (let c=0;c<n;c++) {
      const own = view.own_position && view.own_position[0]==r && view.own_position[1]==c;
      const b = belief[r] ? belief[r][c] : 0;
      const cls = own ? 'own' : (b>0.15?'belief-max':b>0.08?'belief-high':b>0.03?'belief-mid':'belief-low');
      const txt = own ? '★' : (b>0.10?'●':'·');
      html += `<span class="cell ${cls}" title="belief=${b.toFixed(3)}">${txt}</span>`;
    }
    html += '<br>';
  }
  grid.innerHTML = html;
}
</script>
</body>
</html>"""
