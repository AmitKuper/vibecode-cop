"""The replay_page template script half (split from replay_page.py, 150-line rule)."""

SCRIPT = """<script>
let steps=[];let meta=null;
async function loadList(){
  const r=await fetch('/api/replay/logs');const names=await r.json();
  const sel=document.getElementById('logs');
  sel.innerHTML='<option value="">— choose a log —</option>'+names.map(n=>`<option>${n}</option>`).join('');
  sel.onchange=()=>sel.value&&loadLog(sel.value);
  const q=new URLSearchParams(location.search).get('log');
  if(q){sel.value=q;loadLog(q);}
}
async function loadLog(name){
  const r=await fetch('/api/replay/steps?log='+encodeURIComponent(name));
  const d=await r.json();steps=d.steps||[];meta=d.meta||null;
  const v=document.getElementById('verdict');
  v.textContent=d.overall+(meta?`  —  COP: ${meta.our_role==='police'?meta.our_group:meta.opponent_group} · THIEF: ${meta.our_role==='thief'?meta.our_group:meta.opponent_group} (sub-game ${meta.sub_game??'?'})`:'');
  v.className=d.overall==='Verified OK'?'okv':(d.overall.startsWith('RECORDED')?'recv':'badv');
  const s=document.getElementById('slider');
  s.max=Math.max(steps.length-1,0);s.oninput=()=>show(+s.value);
  const i=+(new URLSearchParams(location.search).get('i')||0);
  s.value=Math.min(Math.max(i,0),+s.max);
  show(+s.value);
}
function step(d){
  const s=document.getElementById('slider');
  const v=Math.min(Math.max((+s.value)+d,0),+s.max);
  s.value=v;show(v);
}
document.getElementById('prev').onclick=()=>step(-1);
document.getElementById('next').onclick=()=>step(1);
document.addEventListener('keydown',e=>{
  if(e.key==='ArrowRight'){step(1);e.preventDefault();}
  if(e.key==='ArrowLeft'){step(-1);e.preventDefault();}
});
for(const id of ['tg-cop','tg-thief','tg-scent','tg-scent-cop'])
  document.getElementById(id).onchange=()=>show(+document.getElementById('slider').value);
if(window.self===window.top)document.getElementById('backlink').style.display='inline-block';
const q0=new URLSearchParams(location.search).get('scent');
if(q0){document.getElementById('tg-scent').checked=(q0==='thief'||q0==='both');
  document.getElementById('tg-scent-cop').checked=(q0==='cop'||q0==='both');}
function alpha(v){return 0.12+0.80*Math.min(1,v/0.8);}
function cellBg(vt,vc){
  // thief scent gold, cop scent blue - matching the T / C marker colors
  const gold=vt>0?`rgba(212,164,20,${alpha(vt).toFixed(2)})`:null;
  const blue=vc>0?`rgba(70,130,230,${alpha(vc).toFixed(2)})`:null;
  if(gold&&blue)return `linear-gradient(135deg,${gold} 49%,${blue} 51%)`;
  return gold||blue||'transparent';
}
function show(i){
  if(!steps.length)return;const s=steps[i];const p=s.payload||{};
  document.getElementById('poslabel').textContent=`${i+1}/${steps.length}`;
  const cls=s.ok?'match':'mismatch';
  const rec=(s.board||{}).scent_source==='recorded';
  const who=s.role?(s.role==='police'?'COP':'THIEF'):s.side;
  const grp=meta?(s.side==='ours'?meta.our_group:meta.opponent_group):'';
  document.getElementById('movecard').innerHTML=
    `<div class="legend" style="margin:0 0 4px"><b>${who}</b>${grp?` (${grp})`:''} · ${s.side} · protocol step ${s.step}</div>`+
    `<div>move: <b>${p.move||p.type||'—'}</b> · position: ${JSON.stringify(p.position||null)} · intent: ${p.intent||'—'}</div>`+
    (p.barrier_placed?`<div>barrier placed at <b>${JSON.stringify(p.barrier_placed)}</b></div>`:'')+
    (p.hint?`<div>hint: <i>${String(p.hint).replace(/</g,'&lt;')}</i> <span class="legend">(may lie)</span></div>`:'');
  document.getElementById('stepcard').innerHTML=
    `<div class="hash">stored     : ${s.stored_commit||'—'}</div>`+
    `<div class="hash">recomputed : <span class="${cls}">${s.recomputed_commit||'—'}</span></div>`+
    (rec?`<div>scent: <b>recorded wire bytes</b> (as transmitted, not reconstructed)</div>`
       :`<div>step verdict: <b class="${cls}">${s.ok?'Verified OK':'TAMPERED'}</b></div>`);
  const b=s.board||{};
  document.getElementById('scent-src').innerHTML=b.scent_source==='recorded'
    ?'recorded wire bytes — the fields each side actually transmitted'
    :'reconstructed from the revealed positions<br>via the locked <b>subtractive_chebyshev_v1</b> emitter — wire-exact (peak 0.8)';
  const showC=document.getElementById('tg-cop').checked;
  const showT=document.getElementById('tg-thief').checked;
  const fT=document.getElementById('tg-scent').checked?(b.scent_thief||{}):{};
  const fC=document.getElementById('tg-scent-cop').checked?(b.scent_cop||{}):{};
  const wallSet=new Set((b.barriers||[]).map(w=>`${w[0]},${w[1]}`));
  const n=7;let h='';
  for(let r=0;r<n;r++){for(let c=0;c<n;c++){
    const vt=fT[`${r},${c}`]||0, vc=fC[`${r},${c}`]||0;
    const isC=showC&&b.cop&&b.cop[0]==c&&b.cop[1]==r;
    const isT=showT&&b.thief&&b.thief[0]==c&&b.thief[1]==r;
    // barrier cells travel as [row,col] on the wire — match the scent keys
    const isW=wallSet.has(`${r},${c}`);
    const mark=isC&&isT?'<span class="mark-cop">C</span><span class="mark-thief">T</span>'
      :isC?'<span class="mark-cop">C</span>':isT?'<span class="mark-thief">T</span>':(isW?'&#9632;':'');
    const bg=isW?'#666':cellBg(vt,vc);
    h+=`<div class="cell" style="background:${bg}" title="${isW?'BARRIER · ':''}thief ${vt.toFixed(2)} / cop ${vc.toFixed(2)}">${mark}</div>`;}}
  document.getElementById('board').innerHTML=h;
}
loadList();
</script>
</body>
</html>"""
