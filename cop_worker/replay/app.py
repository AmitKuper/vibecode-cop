"""Replay web application with forward/backward navigation."""

from dataclasses import asdict

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from cop_worker.replay.replay_app import ReplayApp, ReplayState

replay_app_instance: ReplayApp | None = None

app = FastAPI(title="Cop vs Thief — Replay Viewer")


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(_replay_html())


@app.get("/api/status")
async def status() -> JSONResponse:
    if replay_app_instance is None:
        return JSONResponse({"verified": False, "tamper_reason": "No replay loaded"})
    ok, reason = replay_app_instance.verification_status()
    return JSONResponse({"verified": ok, "tamper_reason": reason})


@app.get("/api/state")
async def current() -> JSONResponse:
    if replay_app_instance is None:
        return JSONResponse({"error": "No replay loaded"}, status_code=503)
    return JSONResponse(_state_to_dict(replay_app_instance.current_state()))


@app.post("/api/next")
async def next_step() -> JSONResponse:
    if replay_app_instance is None:
        return JSONResponse({"error": "No replay loaded"}, status_code=503)
    return JSONResponse(_state_to_dict(replay_app_instance.next()))


@app.post("/api/prev")
async def prev_step() -> JSONResponse:
    if replay_app_instance is None:
        return JSONResponse({"error": "No replay loaded"}, status_code=503)
    return JSONResponse(_state_to_dict(replay_app_instance.prev()))


@app.post("/api/first")
async def first_step() -> JSONResponse:
    if replay_app_instance is None:
        return JSONResponse({"error": "No replay loaded"}, status_code=503)
    return JSONResponse(_state_to_dict(replay_app_instance.first()))


@app.post("/api/last")
async def last_step() -> JSONResponse:
    if replay_app_instance is None:
        return JSONResponse({"error": "No replay loaded"}, status_code=503)
    return JSONResponse(_state_to_dict(replay_app_instance.last()))


def _state_to_dict(state: ReplayState) -> dict:
    return asdict(state)


def _replay_html() -> str:
    return """<!DOCTYPE html>
<html>
<head><title>Replay Viewer</title>
<style>
body{font-family:monospace;background:#1a1a2e;color:#e0e0e0;margin:20px}
#verdict{font-size:2em;padding:15px;border-radius:8px;margin-bottom:15px;text-align:center}
.verified{background:#1a5f3f;color:#00ff88}
.tampered{background:#5f1a1a;color:#ff4444}
.controls{margin:10px 0}
button{background:#333;color:#eee;border:1px solid #666;padding:8px 16px;margin:3px;cursor:pointer;border-radius:4px}
button:hover{background:#555}
#event{background:#222;padding:10px;border-radius:5px;white-space:pre-wrap;max-height:400px;overflow:auto}
</style></head>
<body>
<h1>Replay Viewer</h1>
<div id="verdict">Loading...</div>
<div class="controls">
  <button onclick="go('/api/first','POST')">|&lt; First</button>
  <button onclick="go('/api/prev','POST')">&lt; Prev</button>
  <button onclick="go('/api/next','POST')">Next &gt;</button>
  <button onclick="go('/api/last','POST')">Last &gt;|</button>
</div>
<div id="progress"></div>
<pre id="event"></pre>
<script>
async function go(url, method='GET') {
  const r = await fetch(url, {method});
  const data = await r.json();
  const v = document.getElementById('verdict');
  if (data.verified) { v.textContent='VERIFIED OK'; v.className='verified'; }
  else { v.textContent='TAMPERED — ' + (data.tamper_reason||''); v.className='tampered'; }
  document.getElementById('progress').textContent =
    'Gamelet ' + data.gamelet + '  Step ' + data.step + ' / ' + (data.total_steps-1);
  document.getElementById('event').textContent = JSON.stringify(data.event, null, 2);
}
window.onload = () => go('/api/state');
</script>
</body>
</html>"""
