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
th{background:#181826;color:#9ab}
table tr:nth-child(even){background:#161622}
.chip{display:inline-block;background:#1d1d2e;border:1px solid #2a2a3a;border-radius:12px;padding:3px 12px;margin:3px 6px 3px 0}
.kv{max-width:820px}
.rec-w{color:#00ff88;font-weight:bold}.rec-l{color:#ff5566;font-weight:bold}
.win{color:#00ff88}.loss{color:#ff5566}
iframe{border:1px solid #2a2a3a;border-radius:6px;background:#0d0d16}
.lb{display:inline-block;margin:0 26px 12px 0;vertical-align:top}
.lcell{width:32px;height:32px;display:inline-block;border:1px solid #2a2a3a;text-align:center;line-height:32px;vertical-align:top}
.lcell.me{outline:3px solid #ffd447;outline-offset:-3px}
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
<script>
function nav(){
  const view=(location.hash||'#status').slice(1).split('?')[0];
  if(view==='replay'||view==='play'){
    const f=document.getElementById(view+'-frame');
    if(!f.src)f.src='/'+view;
    // keyboard controls live inside the frame - without focus they go dead
    setTimeout(()=>{try{f.contentWindow.focus();}catch(_){}},150);
  }
  for(const v of ['status','history','replay','play','settings']){
    document.getElementById('view-'+v).classList.toggle('show',v===view);
    document.getElementById('nav-'+v).classList.toggle('active',v===view);
  }
}
window.addEventListener('hashchange',nav);
function openReplay(name){
  document.getElementById('replay-frame').src='/replay?log='+encodeURIComponent(name);
  location.hash='#replay';
}
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
    const logs=!(g.logs||[]).length
      ?'<span class="note" title="gamelet log files are kept per game id — a later run against this opponent overwrote this run\\'s logs, so no replay exists">no replay (logs rotated)</span>'
      :(g.logs||[]).map(l=>`<a href="#replay" onclick="openReplay('${l}')">g${l.match(/_g(\\d+)/)?.[1]||'?'}</a>`).join(' ');
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
  document.getElementById('record').innerHTML=
    `${counts.counted} counted: <span class="rec-w">${won}W</span> – <span class="rec-l">${lost}L</span>`+
    `<br><span class="note">${counts.friendly} friendlies · ${counts.local} local</span>`;
  const rec=document.getElementById('t-recent');
  rec.innerHTML='<tr><th>started</th><th>type</th><th>opponent</th><th>score</th><th>winner</th></tr>'+
    list.slice(0,5).map(g=>`<tr><td>${(g.started||'').replace('T',' ')}</td><td>${g.category}</td>`+
      `<td>${g.opponent}</td><td>${g.score}</td>`+
      `<td class="${g.winner==='vibecode'?'win':'loss'}">${g.winner||'—'}</td></tr>`).join('');
}
function liveBoard(v,role){
  const bel=v.belief_heatmap||[],sc=v.opponent_scent||[],own=v.own_position;
  let mx=0;for(const row of bel)for(const x of row)mx=Math.max(mx,x);
  let h=`<div class="lb"><b>${role.toUpperCase()}</b> — sg${v.sub_game||'?'} step ${v.step||'?'}`+
    `${v.your_turn?' · <span class="up">your turn</span>':''} · barriers ${v.barriers_left??'—'}<br>`;
  for(let r=0;r<7;r++){for(let c=0;c<7;c++){
    const b=mx>0?((bel[r]||[])[c]||0)/mx:0, s=(sc[r]||[])[c]||0;
    const red=b>0?`rgba(220,60,60,${(0.08+0.92*b).toFixed(2)})`:null;
    const blue=s>0?`rgba(70,130,230,${(0.12+0.80*Math.min(1,s/0.8)).toFixed(2)})`:null;
    const bg=red&&blue?`linear-gradient(135deg,${red} 49%,${blue} 51%)`:(red||blue||'transparent');
    const me=own&&own[0]==r&&own[1]==c;
    h+=`<span class="lcell${me?' me':''}" style="background:${bg}">${me?'★':''}</span>`;}h+='<br>';}
  return h+'<span class="note">★ own position · red = belief over opponent · blue = sensed scent</span></div>';
}
async function live(){
  const r=await fetch('/api/hub/live');const d=await r.json();
  let fh='';
  for(const role of ['cop','thief']){
    const el=document.getElementById(role+'-st');const v=d[role]||{};
    el.textContent=v.up?`LIVE — sg${v.sub_game||'?'} step ${v.step||'?'}`:'no game running';
    el.className=v.up?'up':'down';
    if(v.up)fh+=liveBoard(v,role);
  }
  document.getElementById('live-frames').innerHTML=fh;
  const hint=document.getElementById('idle-hint');
  if(hint)hint.style.display=fh?'none':'';
}
async function settings(){
  const r=await fetch('/api/hub/settings');const s=await r.json();
  const rows=[['ingress',s.ingress],['our cop / thief ports',`${s.our_cop_port} / ${s.our_thief_port}`],
    ['gui ports (cop / thief)',`${s.gui_cop_port} / ${s.gui_thief_port}`],
    ['scent model',s.scent_model],['move policy',s.move_policy],
    ['friendly report recipient',`${s.report_recipient} (${s.report_mode})`],
    ['counted series played (ledger)',s.counted_played]];
  document.getElementById('t-settings').innerHTML=
    rows.map(([k,v])=>`<tr><td>${k}</td><td>${v??'—'}</td></tr>`).join('');
  document.getElementById('profiles').innerHTML=(s.profiles||[]).map(p=>`<span class="chip">${p}</span>`).join('')||'none';
}
fetch('/api/play/available').then(r=>{if(r.ok)document.getElementById('nav-play').style.display='';}).catch(()=>{});
nav();games();live();settings();setInterval(live,5000);
</script>
</body>
</html>"""
