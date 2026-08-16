"""The live GUI page — five local-truth panels, no build step, SSE-driven.

Panels (book ch.7 + docs/GUI_PRD.md R3): header + turn banner, belief heatmap,
sensed scent, hint + deception cue, integrity ticker. Everything rendered comes
from SafeLiveView; the page has no other data source, so it structurally cannot
show what the agent does not know.
"""

LIVE_PAGE = """<!DOCTYPE html>
<html>
<head><title>Local Truth — Live</title>
<style>
body{font-family:monospace;background:#12121f;color:#e0e0e0;margin:16px}
#hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
#who{font-size:1.3em;font-weight:bold}
#ctx{color:#8888aa}
#banner{font-size:1.6em;font-weight:bold;padding:8px 22px;border-radius:6px}
.your-turn{background:#1a5f3f;color:#00ff88}
.locked{background:#4a4a55;color:#cccccc}
#panels{display:flex;gap:24px;flex-wrap:wrap}
.panel h3{margin:4px 0;color:#9ab}
.cell{width:38px;height:38px;display:inline-block;text-align:center;line-height:38px;border:1px solid #2a2a3a;font-size:15px;vertical-align:top}
.own{outline:3px solid #ffd447;outline-offset:-3px}
#hintbox{margin-top:14px;padding:10px;background:#1d1d2e;border-radius:6px}
#hintbox .warn{color:#ffb347}
#ticker{margin-top:10px;padding:10px;background:#181826;border-radius:6px;color:#aab}
.ok{color:#00ff88}.failed{color:#ff5566}
</style></head>
<body>
<div id="hdr">
  <div><span id="who">—</span> <span id="ctx"></span></div>
  <div id="banner" class="locked">CONNECTING…</div>
</div>
<div id="panels">
  <div class="panel"><h3>Belief over opponent <small>(scent-derived, red ∝ P)</small></h3><div id="belief"></div></div>
  <div class="panel"><h3>Sensed scent <small>(their transmitted field)</small></h3><div id="scent"></div></div>
</div>
<div id="hintbox">💬 their last hint: <span id="hint">(none yet)</span>
  <span class="warn">⚠ may lie — sealed intent ≠ open text</span></div>
<div id="ticker">audits <span id="audits">—</span> · score cop <span id="sc">0</span> – <span id="st">0</span> thief
  · barriers left <span id="bar">—</span>
  · commit sent <span id="cs">—</span> · received <span id="cr">—</span></div>
<script>
function heat(v,max,rgb){const t=max>0?Math.min(1,v/max):0;
  return `rgba(${rgb},${(0.08+0.92*t).toFixed(2)})`;}
function grid(el,m,own,rgb){const n=m.length||7;let mx=0;
  for(const row of m)for(const v of row)mx=Math.max(mx,v);
  let h='';for(let r=0;r<n;r++){for(let c=0;c<n;c++){
    const v=(m[r]||[])[c]||0;const isOwn=own&&own[0]==r&&own[1]==c;
    h+=`<span class="cell${isOwn?' own':''}" style="background:${heat(v,mx,rgb)}" title="${v.toFixed(3)}">${isOwn?'★':''}</span>`;}
  h+='<br>';}el.innerHTML=h;}
function render(view){
  const b=document.getElementById('banner');
  if(view.your_turn){b.textContent='YOUR TURN';b.className='your-turn';}
  else{b.textContent='LOCKED';b.className='locked';}
  document.getElementById('who').textContent=(view.role||'').toUpperCase()||'AGENT';
  document.getElementById('ctx').textContent=
    `sub-game ${view.sub_game||'?'}/${view.num_sub_games||6} · step ${view.turn||'?'} /${view.max_steps||35}`+
    (view.opponent_group?` · vs ${view.opponent_group}`:'');
  grid(document.getElementById('belief'),view.belief_heatmap||[],view.own_position,'220,60,60');
  grid(document.getElementById('scent'),view.opponent_scent||[],view.own_position,'70,130,230');
  document.getElementById('hint').textContent=view.last_hint||'(none yet)';
  const a=(view.audits||[]).map((v,i)=>v?`<span class="${v}">g${i+1}${v=='ok'?'✓':'✗'}</span>`:'').join(' ');
  document.getElementById('audits').innerHTML=a||'—';
  document.getElementById('sc').textContent=(view.score||{}).cop||0;
  document.getElementById('st').textContent=(view.score||{}).thief||0;
  document.getElementById('bar').textContent=view.own_barriers_remaining;
  document.getElementById('cs').textContent=view.last_commit_sent||'—';
  document.getElementById('cr').textContent=view.last_commit_received||'—';
}
const es=new EventSource('/api/stream');
es.onmessage=e=>render(JSON.parse(e.data).view);
fetch('/api/view').then(r=>r.ok?r.json():null).then(d=>d&&d.view&&render(d.view));
</script>
</body>
</html>"""
