# PRD — Live GUI and Replay Viewer (cop repo)

Book authority: chapter 7 ("GUI and Replay Simulator") + the 11.5 pass criteria
("Live GUI and Replay App show `Verified OK`"; submission includes a live
belief-map screenshot and a Verified OK screenshot).

## Product requirements

### R1 — Live GUI, one per role (book 7.3)
Each role runs its OWN GUI served from its own role-worker process
(cop on port 8781 by default). It must show:
- **Belief heatmap** over the opponent's location (red = higher probability),
  with the agent's own cell marked.
- **Turn banner**: green `YOUR TURN` when input is enabled; gray `LOCKED` after
  our commit is sent, until the turn returns.

### R2 — Local truth only (book 7.2, hard constraint)
The GUI may display only what this agent knows: own position, sensed scent,
received hints, its belief. NEVER the opponent's true position or any
bird's-eye state — that violates the Dec-POMDP rules. Enforcement is
structural: the render layer receives a `SafeLiveView` that never contains the
hidden coordinate, and `LiveViewModel._verify_no_hidden_coord` re-verifies on
every update.

### R3 — Extended panels (agreed 2026-08-16, all legal local truth)
- **Sensed scent grid**: the opponent's transmitted `smell_grid` as received,
  on a distinct colour scale (scent = evidence; belief = inference).
- **Hint + deception cue**: opponent's last hint text labelled "may lie"
  (sealed intent vs open text).
- **Integrity ticker**: per-window audit verdicts, running Appendix-F score,
  barriers remaining, last commit sent/received (prefixes).

### R4 — Replay viewer (book 7.4-7.5), BOTH forms
- **CLI** (`scripts/replay_viewer.py`): scriptable verify + interactive
  stepping (n/p/j), per-step recomputed SHA-256 vs stored commitment.
- **Web** (`/replay` on the same app): log picker, timeline slider, per-step
  board from OUR OWN revealed data only, per-step and whole-log verdict.
- One shared verification core; one `TAMPERED` step poisons the whole match.

### R5 — Always-on, fail-open (agreed 2026-08-16)
GUI runs in every game, counted included. Therefore: a dead, hung, or
port-blocked GUI must NEVER delay or block a move. Publish is fire-and-forget;
server start failure (including busy port) is a logged skip, never an error.

## Non-goals
- No input/controls in the live GUI (movement is autonomous).
- No objective board view anywhere, not even in replay (replay reconstructs
  from this side's own revealed records).
- No new UI stack: FastAPI + SSE + one static HTML page, as already shipped.

## Acceptance evidence
1. Full simulated series with GUI on settles 6/6 with the same result as
   GUI off (strength invariance).
2. Serialized `SafeLiveView` stream from a full series contains zero
   occurrences of the opponent's true coordinates.
3. Replay over a real counted log shows `Verified OK`; a 1-byte tamper of a
   copy shows `TAMPERED`.
4. Screenshots filed under evidence/ for the submission.
