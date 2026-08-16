"""The /replay page — timeline with arrows, reconstructed scent, C/T toggles.

Rendered data comes exclusively from the shared verification core plus the
board reconstruction (positions revealed at audit; scent replayed through the
locked emitter). The page computes nothing, so web and CLI verdicts cannot
diverge.
"""

REPLAY_PAGE = """<!DOCTYPE html>
<html>
<head><title>Replay — cryptographic witness</title>
<style>
body{font-family:monospace;background:#12121f;color:#e0e0e0;margin:16px}
#verdict{font-size:1.6em;font-weight:bold;padding:8px 20px;border-radius:6px;display:inline-block;margin:8px 0}
.okv{background:#1a5f3f;color:#00ff88}
.badv{background:#6d1a24;color:#ff5566}
select{width:100%;margin:6px 0}
input[type=range]{margin:6px 8px;vertical-align:middle;width:60%}
button{background:#1d1d2e;color:#e0e0e0;border:1px solid #2a2a3a;border-radius:5px;padding:6px 14px;font-family:monospace;cursor:pointer}
button:hover{background:#25253a}
#stepcard{background:#1d1d2e;border-radius:6px;padding:12px;margin-top:8px}
.hash{word-break:break-all;color:#9ab}
.match{color:#00ff88}.mismatch{color:#ff5566}
#toggles{margin:10px 0;color:#aab}
#toggles label{margin-right:18px;cursor:pointer}
#split{display:flex;gap:26px;flex-wrap:wrap;align-items:flex-start;margin-top:6px}
#board{display:grid;grid-template-columns:repeat(7,44px);gap:2px;width:max-content}
#stepcard{flex:1;min-width:340px;margin-top:0}
.cell{width:44px;height:44px;display:flex;align-items:center;justify-content:center;border:1px solid #2a2a3a;font-weight:bold;font-size:17px;border-radius:3px}
.mark-cop{color:#66aaff;text-shadow:0 0 6px #2244aa}
.mark-thief{color:#ffd447;text-shadow:0 0 6px #aa8800}
.legend{color:#8888aa;font-size:0.9em;margin-top:6px}
</style></head>
<body>
<a id="backlink" href="/#replay" style="display:none;color:#7ab8ff">&#8592; back to dashboard</a>
<h1>Replay viewer — every step re-verified</h1>
<select id="logs"></select>
<div id="verdict" class="badv">select a log</div>
<div>
  <button id="prev" title="previous step (Left arrow)">&#9664; prev</button>
  <input type="range" id="slider" min="0" max="0" value="0">
  <button id="next" title="next step (Right arrow)">next &#9654;</button>
</div>
<div id="poslabel"></div>
<div id="toggles">
  <label><input type="checkbox" id="tg-cop" checked> show cop (C)</label>
  <label><input type="checkbox" id="tg-thief" checked> show thief (T)</label>
  <label><input type="checkbox" id="tg-scent" checked> <span style="color:#d4a414">thief scent</span></label>
  <label><input type="checkbox" id="tg-scent-cop"> <span style="color:#66aaff">cop scent</span></label>
</div>
<div id="split">
  <div>
    <div id="board"></div>
    <div class="legend"><span style="color:#d4a414">&#9632; thief scent</span> ·
    <span style="color:#66aaff">&#9632; cop scent</span> — reconstructed from the revealed
    positions<br>via the locked <b>subtractive_chebyshev_v1</b> emitter — wire-exact (peak 0.8)</div>
  </div>
  <div id="stepcard">(no step)</div>
</div>
<script>
let steps=[];
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
  const d=await r.json();steps=d.steps||[];
  const v=document.getElementById('verdict');
  v.textContent=d.overall;v.className=d.overall==='Verified OK'?'okv':'badv';
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
  document.getElementById('poslabel').textContent=
    `timeline ${i+1}/${steps.length} — ${s.side}, protocol step ${s.step}`;
  const cls=s.ok?'match':'mismatch';
  document.getElementById('stepcard').innerHTML=
    `<div>move: <b>${p.move||p.type||'—'}</b> · position: ${JSON.stringify(p.position||null)} · intent: ${p.intent||'—'}</div>`+
    `<div class="hash">stored     : ${s.stored_commit}</div>`+
    `<div class="hash">recomputed : <span class="${cls}">${s.recomputed_commit}</span></div>`+
    `<div>step verdict: <b class="${cls}">${s.ok?'Verified OK':'TAMPERED'}</b></div>`;
  const b=s.board||{};
  const showC=document.getElementById('tg-cop').checked;
  const showT=document.getElementById('tg-thief').checked;
  const fT=document.getElementById('tg-scent').checked?(b.scent_thief||{}):{};
  const fC=document.getElementById('tg-scent-cop').checked?(b.scent_cop||{}):{};
  const n=7;let h='';
  for(let r=0;r<n;r++){for(let c=0;c<n;c++){
    const vt=fT[`${r},${c}`]||0, vc=fC[`${r},${c}`]||0;
    const isC=showC&&b.cop&&b.cop[0]==c&&b.cop[1]==r;
    const isT=showT&&b.thief&&b.thief[0]==c&&b.thief[1]==r;
    const mark=isC&&isT?'<span class="mark-cop">C</span><span class="mark-thief">T</span>'
      :isC?'<span class="mark-cop">C</span>':isT?'<span class="mark-thief">T</span>':'';
    h+=`<div class="cell" style="background:${cellBg(vt,vc)}" title="thief ${vt.toFixed(2)} / cop ${vc.toFixed(2)}">${mark}</div>`;}}
  document.getElementById('board').innerHTML=h;
}
loadList();
</script>
</body>
</html>"""
