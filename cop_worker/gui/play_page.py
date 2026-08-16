"""The /play page — human vs the production engine, to feel its strength."""

PLAY_PAGE = """<!DOCTYPE html>
<html>
<head><title>Play vs the model</title>
<style>
body{font-family:monospace;background:#12121f;color:#e0e0e0;margin:16px}
button{background:#1d1d2e;color:#e0e0e0;border:1px solid #2a2a3a;border-radius:5px;padding:8px 14px;font-family:monospace;cursor:pointer;margin:2px}
button:hover{background:#25253a}
button.sel{border-color:#7ab8ff;color:#7ab8ff}
#status{font-size:1.2em;font-weight:bold;padding:8px 16px;border-radius:6px;display:inline-block;margin:10px 0;background:#1d1d2e}
#status.win{background:#1a5f3f;color:#00ff88}
#status.lose{background:#6d1a24;color:#ff5566}
#board{display:grid;grid-template-columns:repeat(7,46px);gap:2px;margin:10px 0;width:max-content}
.cell{width:46px;height:46px;display:flex;align-items:center;justify-content:center;border:1px solid #2a2a3a;font-weight:bold;font-size:18px;border-radius:3px}
.barrier{background:#3a3a45;color:#777}
.mark-cop{color:#66aaff;text-shadow:0 0 6px #2244aa}
.mark-thief{color:#ffd447;text-shadow:0 0 6px #aa8800}
.note{color:#8888aa;font-size:0.9em}
#controls{margin:8px 0}
fieldset{border:1px solid #2a2a3a;border-radius:6px;display:inline-block;margin:4px 8px 4px 0;padding:6px 10px}
legend{color:#9ab;font-size:0.85em}
</style></head>
<body>
<h1>Play vs the model <span class="note">— the exact counted engine (hybrid minimax)</span></h1>
<div id="setup">
  <fieldset><legend>your role</legend>
    <button id="r-cop" class="sel">COP (hunt it)</button>
    <button id="r-thief">THIEF (escape it)</button></fieldset>
  <fieldset><legend>engine budget</legend>
    <button id="b-fast">fast (2s/move)</button>
    <button id="b-prod" class="sel">production (10s/move)</button></fieldset>
  <button id="start" style="border-color:#00ff88;color:#00ff88">start game</button>
</div>
<div id="status">choose a role and start</div>
<div id="board"></div>
<div id="controls" style="display:none">
  <fieldset><legend>move (or arrow keys / space=stay)</legend>
    <button data-a="N">▲ N</button><button data-a="S">▼ S</button>
    <button data-a="W">◀ W</button><button data-a="E">▶ E</button>
    <button data-a="STAY">● stay</button></fieldset>
  <fieldset id="barriers-box"><legend>place barrier (<span id="bleft">14</span> left)</legend>
    <button data-a="PLACE_N">▲</button><button data-a="PLACE_S">▼</button>
    <button data-a="PLACE_W">◀</button><button data-a="PLACE_E">▶</button></fieldset>
</div>
<div class="note">scent shown for the model's side · thief moves first each step ·
capture = same cell or barrier on the thief · survive 35 steps to win as thief</div>
<script>
let G=null,role='cop',budget=10.0,busy=false;
function selpair(a,b,idA,idB,on){document.getElementById(idA).classList.toggle('sel',on);
  document.getElementById(idB).classList.toggle('sel',!on);}
document.getElementById('r-cop').onclick=()=>{role='cop';selpair(0,0,'r-cop','r-thief',true);};
document.getElementById('r-thief').onclick=()=>{role='thief';selpair(0,0,'r-cop','r-thief',false);};
document.getElementById('b-fast').onclick=()=>{budget=2.0;selpair(0,0,'b-fast','b-prod',true);};
document.getElementById('b-prod').onclick=()=>{budget=10.0;selpair(0,0,'b-fast','b-prod',false);};
async function api(path,body){
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  return {ok:r.ok,data:await r.json()};
}
document.getElementById('start').onclick=async()=>{
  setStatus('model thinking…','');busy=true;
  const {data}=await api('/api/play/new',{role,budget});
  G=data;busy=false;render();
};
function heat(v){return `rgba(70,130,230,${(0.10+0.85*Math.min(1,v/0.8)).toFixed(2)})`;}
function render(){
  if(!G)return;
  document.getElementById('controls').style.display='';
  document.getElementById('barriers-box').style.display=G.human_role==='cop'?'':'none';
  document.getElementById('bleft').textContent=G.barriers_left;
  const field=G.human_role==='cop'?(G.scent_thief||{}):(G.scent_cop||{});
  const bar=new Set((G.barriers||[]).map(b=>b[0]+','+b[1]));
  let h='';
  for(let r=0;r<7;r++){for(let c=0;c<7;c++){
    const isBar=bar.has(c+','+r);
    const v=field[`${r},${c}`]||0;
    const isC=G.cop&&G.cop[0]==c&&G.cop[1]==r, isT=G.thief&&G.thief[0]==c&&G.thief[1]==r;
    const mark=isBar?'#':(isC&&isT?'CT':isC?'C':isT?'T':'');
    const cls='cell'+(isBar?' barrier':'');
    const style=isBar?'':(v>0?`background:${heat(v)}`:'');
    const mcls=isC?'mark-cop':isT?'mark-thief':'';
    h+=`<div class="${cls}" style="${style}"><span class="${mcls}">${mark}</span></div>`;}}
  document.getElementById('board').innerHTML=h;
  if(G.over){
    const humanWon=(G.outcome==='capture')===(G.human_role==='cop');
    setStatus(G.outcome==='capture'?`CAPTURE at step ${G.step} — ${humanWon?'you win!':'the model got '+(G.human_role==='cop'?'away? no — it caught you':'you')}`
      :`SURVIVAL — 35 steps ${humanWon?'— you escaped the model!':'— the model escaped you'}`,
      humanWon?'win':'lose');
  } else {
    setStatus(`step ${G.step}/35 — your move`+(G.last_model_action?` (model played ${G.last_model_action})`:''),'');
  }
}
function setStatus(t,cls){const s=document.getElementById('status');s.textContent=t;s.className=cls;}
async function move(a){
  if(!G||G.over||busy)return;
  busy=true;setStatus('model thinking…','');
  const {ok,data}=await api('/api/play/move',{game:G.id,action:a});
  busy=false;
  if(!ok){setStatus('illegal move — try another','');return;}
  G=data;render();
}
document.querySelectorAll('#controls button').forEach(b=>b.onclick=()=>move(b.dataset.a));
document.addEventListener('keydown',e=>{
  const map={ArrowUp:'N',ArrowDown:'S',ArrowLeft:'W',ArrowRight:'E',' ':'STAY'};
  if(map[e.key]!==undefined){move(map[e.key]);e.preventDefault();}
});
</script>
</body>
</html>"""
