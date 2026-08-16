"""The dashboard home page: game history + live-panel status, all local truth."""

HUB_PAGE = """<!DOCTYPE html>
<html>
<head><title>Cop/Thief — Dashboard</title>
<style>
body{font-family:monospace;background:#12121f;color:#e0e0e0;margin:16px}
h1{margin:4px 0}
.cards{display:flex;gap:16px;margin:12px 0}
.card{background:#1d1d2e;border-radius:8px;padding:12px 16px;min-width:220px}
.up{color:#00ff88}.down{color:#8888aa}
a{color:#7ab8ff}
table{border-collapse:collapse;margin-top:8px}
td,th{border:1px solid #2a2a3a;padding:6px 12px;text-align:left}
.win{color:#00ff88}.loss{color:#ff5566}
iframe{border:1px solid #2a2a3a;border-radius:6px;background:#0d0d16}
</style></head>
<body>
<h1>Cop/Thief dashboard</h1>
<div class="cards">
  <div class="card"><b>COP live view</b> — <span id="cop-st" class="down">checking…</span><br>
    <a href="http://127.0.0.1:8781/" target="_blank">open ↗</a></div>
  <div class="card"><b>THIEF live view</b> — <span id="thief-st" class="down">checking…</span><br>
    <a href="http://127.0.0.1:8782/" target="_blank">open ↗</a></div>
  <div class="card"><b>Replay viewer</b><br><a href="/replay">browse logs ↗</a></div>
</div>
<div id="live-frames"></div>
<h2>Game history</h2>
<table id="games"><tr><th>game</th><th>windows</th><th>score</th><th>winner</th>
<th>mutual sha</th><th>replay</th></tr></table>
<script>
async function games(){
  const r=await fetch('/api/hub/games');const list=await r.json();
  const t=document.getElementById('games');
  for(const g of list){
    const won=g.winner==='vibecode';
    const logs=(g.logs||[]).map(l=>`<a href="/replay?log=${encodeURIComponent(l)}">g${l.match(/_g(\\d+)/)?.[1]||'?'}</a>`).join(' ');
    t.insertAdjacentHTML('beforeend',
      `<tr><td>${g.game_id}</td><td>${g.windows}</td><td>${g.score}</td>`+
      `<td class="${won?'win':'loss'}">${g.winner||'—'}</td>`+
      `<td title="${g.mutual_sha||''}">${(g.mutual_sha||'').slice(0,12)}${g.confirmed?' ✓':''}</td>`+
      `<td>${logs}</td></tr>`);
  }
}
async function live(){
  const r=await fetch('/api/hub/live');const d=await r.json();
  const frames=document.getElementById('live-frames');let fh='';
  for(const role of ['cop','thief']){
    const el=document.getElementById(role+'-st');const up=d[role]&&d[role].up;
    el.textContent=up?`LIVE — sg${d[role].sub_game||'?'} step ${d[role].step||'?'}`:'no game running';
    el.className=up?'up':'down';
    if(up)fh+=`<iframe src="http://127.0.0.1:${role==='cop'?8781:8782}/" width="49%" height="620"></iframe>`;
  }
  frames.innerHTML=fh;
}
games();live();setInterval(live,5000);
</script>
</body>
</html>"""
