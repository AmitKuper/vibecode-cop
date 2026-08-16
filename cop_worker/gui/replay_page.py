"""The /replay page — timeline slider over a verified reference-v3 log.

Rendered data comes exclusively from the shared verification core
(cop_worker.replay.ref3_steps); the page itself computes nothing, so the web
verdict and the CLI verdict cannot diverge.
"""

REPLAY_PAGE = """<!DOCTYPE html>
<html>
<head><title>Replay — cryptographic witness</title>
<style>
body{font-family:monospace;background:#12121f;color:#e0e0e0;margin:16px}
#verdict{font-size:1.8em;font-weight:bold;padding:10px 24px;border-radius:6px;display:inline-block;margin:8px 0}
.okv{background:#1a5f3f;color:#00ff88}
.badv{background:#6d1a24;color:#ff5566}
select,input[type=range]{width:100%;margin:6px 0}
#stepcard{background:#1d1d2e;border-radius:6px;padding:12px;margin-top:8px}
.hash{word-break:break-all;color:#9ab}
.match{color:#00ff88}.mismatch{color:#ff5566}
#board{margin-top:8px}
.cell{width:34px;height:34px;display:inline-block;text-align:center;line-height:34px;border:1px solid #2a2a3a}
.here{background:#2244aa;color:#ffd447;font-weight:bold}
</style></head>
<body>
<h1>Replay viewer — every step re-verified</h1>
<select id="logs"></select>
<div id="verdict" class="badv">select a log</div>
<input type="range" id="slider" min="0" max="0" value="0">
<div id="poslabel"></div>
<div id="stepcard">(no step)</div>
<div id="board"></div>
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
  s.max=Math.max(steps.length-1,0);s.value=0;s.oninput=()=>show(+s.value);
  show(0);
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
  const n=7;let h='';
  const pos=Array.isArray(p.position)?p.position:null;
  for(let r=0;r<n;r++){for(let c=0;c<n;c++){
    const here=pos&&pos[0]==c&&pos[1]==r;  // wire [x,y] -> row r, col c
    h+=`<span class="cell${here?' here':''}">${here?(s.side==='ours'?'U':'O'):''}</span>`;}
  h+='<br>';}
  document.getElementById('board').innerHTML=h;
}
loadList();
</script>
</body>
</html>"""
