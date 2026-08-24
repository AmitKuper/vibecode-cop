"""The dashboard: left sidebar (Status / Game History / Settings), local truth only."""

from cop_worker.gui.hub_page_js import SCRIPT as _SCRIPT

HUB_PAGE = (
    """<!DOCTYPE html>
<html>
<head><title>Cop/Thief — Dashboard</title>
<style>
body{font-family:monospace;background:#12121f;color:#e0e0e0;margin:0;display:flex;min-height:100vh}
#side{width:190px;background:#181826;padding:16px 0;flex-shrink:0}
#side h1{font-size:1.05em;padding:0 16px;margin:0 0 14px}
#side a{display:block;padding:10px 16px;color:#aab;text-decoration:none;border-left:3px solid transparent}
#side a.active{color:#fff;background:#1d1d2e;border-left-color:#7ab8ff}
#main{flex:1;padding:18px 22px;min-width:0}
.view{display:none}.view.show{display:block}
h2{margin:6px 0 10px}
.cards{display:flex;gap:16px;margin:12px 0;flex-wrap:wrap}
.card{background:#1d1d2e;border-radius:8px;padding:12px 16px;min-width:210px}
.up{color:#00ff88}.down{color:#8888aa}
a{color:#7ab8ff}
table{border-collapse:collapse;margin:8px 0 18px;width:100%}
td,th{border:1px solid #2a2a3a;padding:6px 10px;text-align:left}
th{background:#181826;color:#9ab}
table tr:nth-child(even){background:#161622}
.chip{display:inline-block;background:#1d1d2e;border:1px solid #2a2a3a;border-radius:12px;padding:3px 12px;margin:3px 6px 3px 0}
.kv{max-width:820px}
.rec-w{color:#00ff88;font-weight:bold}.rec-l{color:#ff5566;font-weight:bold}
.win{color:#00ff88}.loss{color:#ff5566}
iframe{border:1px solid #2a2a3a;border-radius:6px;background:#0d0d16}
.kv td:first-child{color:#9ab;width:220px}
.note{color:#8888aa;font-size:0.9em}
</style></head>
<body>
<nav id="side">
  <h1>Cop/Thief</h1>
  <a href="#status" id="nav-status">Status</a>
  <a href="#history" id="nav-history">Game History</a>
  <a href="#replay" id="nav-replay">Replay</a>
  <a href="#play" id="nav-play" style="display:none">Play vs Model</a>
  <a href="#settings" id="nav-settings">Settings</a>
</nav>
<div id="main">

<div class="view" id="view-status">
  <h2>Status</h2>
  <div class="cards">
    <div class="card"><b>COP live view</b> — <span id="cop-st" class="down">checking…</span><br>
      <a href="http://127.0.0.1:8781/" target="_blank">open ↗</a></div>
    <div class="card"><b>THIEF live view</b> — <span id="thief-st" class="down">checking…</span><br>
      <a href="http://127.0.0.1:8782/" target="_blank">open ↗</a></div>
    <div class="card"><b>League record</b><br><span id="record">—</span></div>
  </div>
  <div id="live-frames"></div>
  <p class="note" id="idle-hint">Live panels light up here automatically when a match runs.
  Meanwhile: step through <a href="#history">Game History</a> or take on the engine in
  <a href="#play">Play vs Model</a>.</p>
  <h2>Recent games</h2>
  <table id="t-recent"></table>
</div>

<div class="view" id="view-history">
  <h2>Counted game history <small>(filed with the league)</small></h2>
  <table id="t-counted"></table>
  <h2>Friendly game history <small>(every run; recovered runs have no replay links — gamelet logs rotate per game)</small></h2>
  <table id="t-friendly"></table>
  <h2>Human vs model <small>(play-page games against the production engine)</small></h2>
  <table id="t-human"></table>
  <h2>Local / simulated game history <small>(peer simulator, kit sparring)</small></h2>
  <table id="t-local"></table>
</div>

<div class="view" id="view-replay">
  <h2>Replay <a class="note" href="/replay" target="_blank">open full page ↗</a></h2>
  <iframe id="replay-frame" style="width:100%;height:82vh" loading="lazy"></iframe>
</div>

<div class="view" id="view-play">
  <h2>Play vs the model <a class="note" href="/play" target="_blank">open full page ↗</a></h2>
  <iframe id="play-frame" style="width:100%;height:84vh" loading="lazy"></iframe>
</div>

<div class="view" id="view-settings">
  <h2>Settings <span class="note">(read-only — the dashboard never writes; edit config/runtime.toml)</span></h2>
  <table class="kv" id="t-settings"></table>
  <h2>Opponent profiles</h2>
  <div id="profiles" class="note"></div>
</div>

</div>
"""
    + _SCRIPT
)
