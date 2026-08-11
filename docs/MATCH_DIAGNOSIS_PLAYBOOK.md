# Match diagnosis playbook — log signature → instruction for the other group

For live sessions: paste the tail of `vibecode-cop/reports/ref3_matches/match_<opp>_<ts>.log`
(every line is wall-clock stamped) and match it against this table. Each row ends with
the sentence to relay to the other group when the fault is on THEIR side.

## Where the evidence lives

| artifact | contents |
|---|---|
| `reports/ref3_matches/match_*.log` | timestamped everything: `[match]` phases, `[wire<-]` per-inbound-message metadata, `[diag]` refusal diffs, retries, tracebacks |
| `reports/ref3_matches/last_match_result.json` | full internal snapshot: our sealed records, their audit records + per-step declared barrier/claim/hint, disputes, identities |
| `artifacts/` (per game) | the league-schema config/declaration/log/result files |

## Before/at connection

| log signature | meaning | instruction to them |
|---|---|---|
| probe answers **406** | their endpoint healthy (MCP refusing a bare GET) | none — this is the READY state |
| probe answers **502** | their tunnel/edge up, **no peer bound behind it** | "Your edge answers 502 — your agent isn't bound to the tunnel. Start your peer process." |
| probe answers **530** | edge up, origin unreachable | "Your tunnel can't reach your origin — your local process or its port died. Restart the process, not the tunnel." |
| **404 + ERR_NGROK_3200** | tunnel client itself is gone | "Your tunnel agent is disconnected — the URL is fine, nothing behind it. Restart the tunnel client." |
| `peer window never opened` after 900s, probes healthy (406) | they're up but never dialed / wrong window | "Your endpoint answers but your runner never opened sub-game N against us — check your window scheduler and that you dialed OUR urls." |

## Handshake

| log signature | meaning | instruction to them |
|---|---|---|
| no `[wire<-] negotiate` line at all for the sub-game | their greeting NEVER arrived | "We received zero negotiate calls from you (our inbound log is empty for sg N at HH:MM). Are you dialing http://62.56.220.143:6122{4,3}/mcp, tool `negotiate`, arg `message`?" |
| `[wire<-] negotiate` with `sub_game=<wrong n>` only | stale re-pushed greetings, their runner lags | "Your greetings still carry sub_game=K while we're at N — your runner didn't advance. Restart your sub-game N window." |
| `HANDSHAKE REFUSED: SPAR-N02` + `[diag] terms key diff` | terms key set differs (e.g. missing `min_center_intensity`) | "Your flat terms lack/add the keys in our diff line — emit exactly the kit's 14 (`sparring/config.py TERMS_KEYS`); `min_center_intensity` defaults 0.5." |
| `SPAR-N03` + `[diag] terms value diff` | same keys, different values | "Your terms differ on the named keys — reconcile game.json values with the agreed constitution (sha da1c9108…)." |
| `SPAR-N04` | their signature doesn't verify over their nonce | "Your terms signature doesn't reproduce: construction is SHA256(canonical_json(terms) + single pipe + nonce), compact separators, sorted keys." |
| `SPAR-N05` + `[diag] locks` | lock hash mismatch (both declared) | "Your scent_model_sha256 is X, ours is 81ebee59… (subtractive_chebyshev_v1, recomputed from the kit). Redeclare or recompute yours." |
| `SPAR-N06 / N07` | sub-game index / role collision | "Your greeting names sub_game/role in the diag line — restart exactly one side with the other role / correct index (odd = your police vs our thief)." |
| `SPAR-N10` + `[diag] uid` | game_uid mismatch, both declared | "Your uid differs from ours (2e167349-…). Derive from the FLAT 14-key signed terms + sorted pair — never the whole game.json." |

## During play

| log signature | meaning | instruction to them |
|---|---|---|
| `timeout … waiting for opponent turn step K; their last inbound turn=(K-1, …, HH:MM:SS)` | THEY stalled mid-game | "Your step K never arrived; your last turn was K-1 at HH:MM:SS (our stamped log). Your turn loop is stuck — if your process is alive, check whether you're waiting on a reply from us that already returned 200 (push vs request/response)." |
| same, but `their last inbound turn=NONE EVER` | they never played at all | "We completed the handshake but zero turns arrived. Your sender may be posting to the wrong role port — cop turns go to our thief endpoint (:61223) and vice versa." |
| `[wire<-] turn … step=` NOT advancing + our sends erroring in retries | their receiver rejects us | "Your receive_turn returns errors on our turns (see our retry lines at HH:MM) — what does your validation refuse? Our turns carry the ten keys, non-empty ISO timestamp, lowercase hex commit." |
| `*** PEER SCENT MODEL MISMATCH ***` | their field isn't the locked model | log-only, no refusal: "Your smell_grid classifies as <model> — we locked subtractive_chebyshev_v1. Not fatal tonight, but fix before the counted game." |
| `equivocation` / `different commit` in a traceback | they re-sent a step under a NEW commit | "Your step K was re-sent with a different commit — a re-send must carry identical bytes. Your retry path is re-sealing." |
| barriers behaving impossibly / thief 'dodging through' our wall | cell convention mismatch | "Confirm your cell fields are [row, col] (kit convention, same as smell keys). If you send [x, y], every off-diagonal cell is transposed — this is the question in our pairing note." |

## Settlement

| log signature | meaning | instruction to them |
|---|---|---|
| `timeout waiting for audit` | they never sent submit_audit | "Sub-game N settled on our side at HH:MM but your submit_audit never arrived — send it (payload: sender, records, result_claim) or the sub-game reads as unsettled." |
| `audit ok=False errors=[…commitment mismatch…]` | their revealed records don't rehash | "Your record for step K doesn't reproduce its commit — check you reveal the exact sealed payload + nonce, single-pipe construction." |
| `…missing or revealed under another commit` | their audit omits a played step / re-sealed | "Your audit is missing step K that you played live at HH:MM (we hold the arrived commit) — disclose every step you sent." |
| `did NOT corroborate (concession…)` / `trail_end_mismatch` | their caught=true doesn't check out | recorded as DISPUTED, not accused: "Your concession names cell C but our barrier record / your revealed trail doesn't support it — let's compare records before either side reports." |
| `REPORT WITHHELD` on our side | <6 settled sub-games | correct behaviour (rule 35): finish/settle the missing windows or NOBODY reports. |

## Ground rules for the live session

- Never debug inside a window: kill, name a new T (their §5 — we agreed).
- An instruction to them always cites OUR stamped log line (time + `[wire<-]`/`[diag]` content) — evidence, not guesswork.
- Our own likely-fault signatures: port-preflight refusal at start (stray process — kill it),
  obs-mode guard refusal at load (env vs manifest — don't override, fix the env),
  `mcp_call_sec` refusal (config), repeated send retries with THEIR endpoint 406-healthy
  (our network path — check our router/forwarding).
