"""The hub_page template script half (split from hub_page.py, 150-line rule)."""

SCRIPT = """<script>
function nav(){
  const view=(location.hash||'#status').slice(1).split('?')[0];
  if(view==='replay'){
    const f=document.getElementById('replay-frame');
    if(!f.src)f.src='/replay';
  }
  if(view==='play'){
    const f=document.getElementById('play-frame');
    if(!f.src)f.src='/play';
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
  const tables={counted:'t-counted',friendly:'t-friendly',local:'t-local',human:'t-human'};
  for(const [cat,id] of Object.entries(tables))
    document.getElementById(id).innerHTML=header(cat);
  const counts={counted:0,friendly:0,local:0};let won=0,lost=0;
  for(const g of list){
    const t=document.getElementById(tables[g.category]||'t-local');
    counts[g.category]=(counts[g.category]||0)+1;
    const w=g.winner==='vibecode';
    if(g.category==='counted'){w?won++:lost++;}
    const logs=!(g.logs||[]).length?'<i>rotated</i>':(g.logs||[]).map(l=>`<a href="#replay" onclick="openReplay('${l}')">g${l.match(/_g(\\d+)/)?.[1]||'?'}</a>`).join(' ');
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
