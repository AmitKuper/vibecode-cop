# RL policy model card — cop

Status: **SHIPPED** — manifest-selected model behind the counted win vs
`imreeyal` (90–30, 6/6 audits Verified OK, 2026-08-10).

## Identity and intended use

- Role: cop; grid: 7×7; algorithm: `RecurrentA2C-GRU`
  (linear–tanh–GRUCell–policy/value heads, hidden size 128).
- Artifact: `models/cop_chebyshev_champion.pt`.
- SHA-256:
  `a59e0a6cafffcf2351798a8b78c3c3518b44d80a4871c4a345367421238657ba`.
- Training-code SHA: `cdb736b`; binding `config/game.json` SHA-256:
  `da1c9108c5989ac5634bae374dc6b90de4389135a699000bfe52f76ec43743ff`.
- Inference: deterministic argmax after the canonical legal-action mask.
- **Intended use: blind-frame fallback inside the `hybrid_search` serving
  engine.** Under the locked `subtractive_chebyshev_v1` scent model the
  transmitted frame's unique 0.8 peak is the emitter's cell, so sighted frames
  are played by the deterministic minimax engine
  (`cop_worker/rl/pursuit_search.py` via `search_policy.py`); this net moves
  only when the frame is blind or ambiguous.

## Observation mode (recorded in `models/MANIFEST.json`, guard-enforced)

| Key | Value |
|---|---|
| `uniform_belief` | `true` (production feeds `BeliefState.uniform`) |
| `wire_scent` | `false` |
| `decoded_scent` | `false` |
| `scent_model` | `subtractive_chebyshev_v1` |

The obs-mode serving guard refuses to load an artifact whose recorded
`scent_model` does not match the environment, and refuses stray
`COPTHIEF_DECODED_SCENT`/`COPTHIEF_SCENT_MODEL` overrides at serving time.

## Training recipe

From-scratch chebyshev run of 2026-08-10 (no book-model ancestry): env
`COPTHIEF_UNIFORM_BELIEF=1 COPTHIEF_SCENT_MODEL=chebyshev`, seed 20260820,
21,000 training steps, gamma 0.99, hidden size 128, and
**`fixed_start_fraction = 0.8`** — 80% of training episodes open at the signed
match starts (`cop_start [0,0]` / `thief_start [3,3]`), because match starts
are signed Step-0 terms and every counted game opens there.

## Evaluation (honest harness: `scripts/eval_candidate.py`, fixed configured starts, seed 20260810, 30 games/family, scent=chebyshev / belief=prod)

| Policy | Win rate |
|---|---:|
| **This model (fixed-start fraction 0.8)** | **0.9926** |
| Fixed-start fraction 0.5 (rejected A/B arm) | 0.9889 |
| Random-start recipe (gen01, superseded same day) | 0.8704 |
| Superseded book champion under the chebyshev field | 0.2148 |

Arena context (why the net is fallback-only): the search engine captures the
best chebyshev RL thieves 12/12 at depth 3, while the best RL cop scores 0/12
against the search thief. Full matrices, archetype sweep, and depth/latency
data: `docs/RL_RESEARCH_REPORT_20260810.md`.

## Live validation

Rehearsal 3/3 captures (~step 13); friendly ×2 and the counted series vs
imreeyal all 90–30 with cop captures in every even window (steps 14/16/16 in
friendly #1). Every live half-move stayed inside the 10 s search budget.

## Limitations

- Specialized to the 7×7 board, the signed starts, and
  `subtractive_chebyshev_v1`; a different Step-0 scent lock requires a
  different artifact (the guard enforces this).
- The 0.8 fixed-start bias trades start-generalization for opening strength —
  measured as the right trade for pursuit, and the opposite of the thief's
  outcome (see the A/B in the research report).
- Fallback-only in production: headline strength comes from the minimax
  engine; this card's numbers describe the net alone.
- Training-resume caveat: resumed cop generations regressed monotonically
  (gen01 0.933 → gen09 0.32 in-run); retrain fresh rather than fine-tune.

---

## Superseded models (kept for rollback, no longer manifest-selected)

### `models/cop_population_oracle_champion.pt` — book-model line champion

Population-oracle distilled `RecurrentA2C-GRU` (SHA-256 `9c5aee7f…`), the
2026-08-09 champion under `multiplicative_book_v1` scent and the binding
`game.json` `9d6ec544…`. Started from the previous recurrent champion plus
9,264 sequence examples from 600 population-oracle teacher games (200 updates,
lr 3e-4, seed 20260809, 492,264 cumulative steps; teacher population: anti-loop,
scent, wall, corridor, targeted, local-adversarial, prior learned strategies).

Held-out fixed-start ten-family tournament (20 six-gamelet series per family):
1,153/1,200 captures = 96.08% (Wilson 95%: 94.83–97.04%) vs the prior
champion's 902/1,200 = 75.17%; official score 23,295–6,235; worst-family
71.67% vs 0%; p99 inference 4.51 ms. Method and experiment inventory:
`docs/RL_RESEARCH_REPORT_20260809.md`; machine evidence:
`results/rl/research_20260809/`.

Superseded because the imreeyal Step-0 locked `subtractive_chebyshev_v1`:
under that field this model measures **0.2148** on the honest harness. Its
in-family win rates were also never reproduced on the wire — the counted
series it informed (vs anrbj666) was lost 35–75.

### `models/cop_recurrent_champion.pt` — earlier recurrent champion

Pre-distillation rollback checkpoint of the book-model line (75.17% on the
same held-out suite). Retained for provenance only.
