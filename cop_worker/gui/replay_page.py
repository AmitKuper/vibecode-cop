"""The /replay page — timeline with arrows, reconstructed scent, C/T toggles.

Rendered data comes exclusively from the shared verification core plus the
board reconstruction (positions revealed at audit; scent replayed through the
locked emitter). The page computes nothing, so web and CLI verdicts cannot
diverge.
"""

from cop_worker.gui.replay_page_js import SCRIPT as _SCRIPT

REPLAY_PAGE = (
    """<!DOCTYPE html>
<html>
<head><title>Replay — cryptographic witness</title>
<style>
/* One column width drives everything: the board is 7*44 + 6*2 = 320px, so
   both split columns are 320px and the page is 2*320 + gap. Every block on
   the page then lines up on the same left and right edge. */
:root{--col:320px;--gap:26px;--page:calc(2*var(--col) + var(--gap))}
*{box-sizing:border-box}
body{font-family:monospace;background:#12121f;color:#e0e0e0;margin:16px;text-align:center}
#page{width:var(--page);max-width:100%;margin:0 auto}
#verdict{font-size:1.6em;font-weight:bold;padding:8px 20px;border-radius:6px;display:block;width:100%;margin:8px 0}
.okv{background:#1a5f3f;color:#00ff88}
.badv{background:#6d1a24;color:#ff5566}
.recv{background:#23345c;color:#9ab8e8}
select{display:block;width:100%;margin:6px 0}
#movecard{background:#1d1d2e;border-radius:6px;padding:10px 12px;margin:8px 0 0;text-align:left;font-size:0.92em}
#leftcol{flex:0 0 var(--col);width:var(--col);text-align:center;display:flex;flex-direction:column}
#leftcol .legend{text-align:left}
#navrow{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:2px}
#navrow button{padding:4px 10px}
#poslabel{font-size:0.9em;color:#aab}
input[type=range]{display:block;width:100%;margin:8px 0 2px}
button{background:#1d1d2e;color:#e0e0e0;border:1px solid #2a2a3a;border-radius:5px;padding:6px 14px;font-family:monospace;cursor:pointer}
button:hover{background:#25253a}
.hash{word-break:break-all;color:#9ab}
.match{color:#00ff88}.mismatch{color:#ff5566}
#toggles{margin:10px 0;color:#aab;width:100%}
#toggles label{margin-right:18px;cursor:pointer}
#toggles label:last-child{margin-right:0}
#split{display:flex;gap:var(--gap);flex-wrap:wrap;align-items:stretch;justify-content:center;margin-top:6px;width:100%}
#board{display:grid;grid-template-columns:repeat(7,44px);gap:2px;width:max-content;margin:0 auto}
#stepcard{background:#1d1d2e;border-radius:6px;padding:12px;flex:0 0 var(--col);width:var(--col);margin-top:0;text-align:left}
.cell{width:44px;height:44px;display:flex;align-items:center;justify-content:center;border:1px solid #2a2a3a;font-weight:bold;font-size:17px;border-radius:3px}
.mark-cop{color:#66aaff;text-shadow:0 0 6px #2244aa}
.mark-thief{color:#ffd447;text-shadow:0 0 6px #aa8800}
.legend{color:#8888aa;font-size:0.9em;margin-top:6px}
</style></head>
<body>
<div id="page">
<a id="backlink" href="/#replay" style="display:none;color:#7ab8ff">&#8592; back to dashboard</a>
<h1>Replay viewer — every step re-verified</h1>
<select id="logs"></select>
<div id="verdict" class="badv">select a log</div>
<div id="toggles">
  <label><input type="checkbox" id="tg-cop" checked> show cop (C)</label>
  <label><input type="checkbox" id="tg-thief" checked> show thief (T)</label>
  <label><input type="checkbox" id="tg-scent" checked> <span style="color:#d4a414">thief scent</span></label>
  <label><input type="checkbox" id="tg-scent-cop"> <span style="color:#66aaff">cop scent</span></label>
</div>
<div id="split">
  <div id="leftcol">
    <div id="board"></div>
    <input type="range" id="slider" min="0" max="0" value="0">
    <div id="navrow"><button id="prev" title="previous step (Left arrow)">&#9664; prev</button>
      <span id="poslabel"></span>
      <button id="next" title="next step (Right arrow)">next &#9654;</button></div>
    <div id="movecard">(no step)</div>
    <div class="legend"><span style="color:#d4a414">&#9632; thief scent</span> ·
    <span style="color:#66aaff">&#9632; cop scent</span> — <span id="scent-src">reconstructed from
    the revealed positions<br>via the locked <b>subtractive_chebyshev_v1</b> emitter — wire-exact
    (peak 0.8)</span></div>
  </div>
  <div id="stepcard">(no step)</div>
</div>
</div>
"""
    + _SCRIPT
)
