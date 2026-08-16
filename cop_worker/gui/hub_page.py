"""The dashboard: left sidebar (Status / Game History / Settings), local truth only."""

HUB_PAGE = """<!DOCTYPE html>
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
  <a href="#settings" id="nav-settings">Settings</a>
  <a href="/replay">Replay viewer ↗</a>
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
</div>

<div class="view" id="view-history">
  <h2>Counted game history <small>(filed with the league)</small></h2>
  <table id="t-counted"></table>
  <h2>Friendly game history <small>(every run; recovered runs have no replay links — gamelet logs rotate per game)</small></h2>
  <table id="t-friendly"></table>
  <h2>Local / simulated game history <small>(peer simulator, kit sparring)</small></h2>
  <table id="t-local"></table>
</div>

<div class="view" id="view-settings">
  <h2>Settings <span class="note">(read-only — the dashboard never writes; edit config/runtime.toml)</span></h2>
  <table class="kv" id="t-settings"></table>
  <h2>Opponent profiles</h2>
  <div id="profiles" class="note"></div>
</div>

</div>
<script>
function nav(){
  const view=(location.hash||'#status').slice(1);
  for(const v of ['status','history','settings']){
    document.getElementById('view-'+v).classList.toggle('show',v===view);
    document.getElementById('nav-'+v).classList.toggle('active',v===view);
  }
}
window.addEventListener('hashchange',nav);
function header(cat){
  return '<tr><th>game</th><th>group</th><th>opponent group</th><th>windows</th>'+
    '<th>started</th><th>score</th><th>winner</th><th>mutual sha</th>'+
    (cat==='counted'?'<th>league report id</th>':'')+'<th>replay</th></tr>';
}
async function games(){
  const r=await fetch('/api/hub/games');const list=await r.json();
  const tables={counted:'t-counted',friendly:'t-friendly',local:'t-local'};
  for(const [cat,id] of Object.entries(tables))
    document.getElementById(id).innerHTML=header(cat);
  const counts={counted:0,friendly:0,local:0};let won=0,lost=0;
  for(const g of list){
    const t=document.getElementById(tables[g.category]||'t-local');
    counts[g.category]=(counts[g.category]||0)+1;
    const w=g.winner==='vibecode';
    if(g.category==='counted'){w?won++:lost++;}
    const logs=!(g.logs||[]).length?'<i>rotated</i>':(g.logs||[]).map(l=>`<a href="/replay?log=${encodeURIComponent(l)}">g${l.match(/_g(\\d+)/)?.[1]||'?'}</a>`).join(' ');
    t.insertAdjacentHTML('beforeend',
      `<tr><td>${g.game_id}</td><td>${g.group}</td><td>${g.opponent}</td>`+
      `<td>${g.windows}</td><td>${(g.started||'').replace('T',' ')}</td><td>${g.score}</td>`+
      `<td class="${w?'win':'loss'}">${g.winner||'—'}</td>`+
      `<td title="${g.mutual_sha||''}">${(g.mutual_sha||'').slice(0,12)}${g.confirmed?' ✓':''}</td>`+
      (g.category==='counted'?`<td>${g.report_id||'—'}</td>`:'')+
      `<td>${logs}</td></tr>`);
  }
  for(const [cat,id] of Object.entries(tables))
    if(!counts[cat])document.getElementById(id).insertAdjacentHTML('beforeend',
      '<tr><td colspan="10" class="note">none yet</td></tr>');
  document.getElementById('record').textContent=
    `${counts.counted} counted: ${won}W – ${lost}L · ${counts.friendly} friendlies · ${counts.local} local`;
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
async function settings(){
  const r=await fetch('/api/hub/settings');const s=await r.json();
  const rows=[['ingress',s.ingress],['our cop / thief ports',`${s.our_cop_port} / ${s.our_thief_port}`],
    ['gui ports (cop / thief)',`${s.gui_cop_port} / ${s.gui_thief_port}`],
    ['scent model',s.scent_model],['move policy',s.move_policy],
    ['friendly report recipient',`${s.report_recipient} (${s.report_mode})`],
    ['counted series played',s.counted_played]];
  document.getElementById('t-settings').innerHTML=
    rows.map(([k,v])=>`<tr><td>${k}</td><td>${v??'—'}</td></tr>`).join('');
  document.getElementById('profiles').textContent=(s.profiles||[]).join(' · ')||'none';
}
nav();games();live();settings();setInterval(live,5000);
</script>
</body>
</html>"""
