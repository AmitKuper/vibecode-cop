# Handoff: no-LLM practice mode + 10×10 model training

**For the agent picking this up.** This covers two things: (1) what already exists and
works — a keyboard-driven practice mode against the trained champion, pure RL, zero LLM
calls — and (2) a new task: train a second pair of champions (cop + thief) for a **10×10**
grid using the exact same training method used for the existing 7×7 champions, since that
method produced decent results (cop 83.3% overall win rate / 48.3% worst-family; thief
79.1%).

---

## Part 1 — What already works (read first, don't re-derive it)

`scripts/human_vs_rl.py` (this repo) is a standalone, additive script — it does not modify
or depend on any other file, safe to delete any time. It loads
`models/cop_recurrent_champion.pt` via `models/MANIFEST.json` and lets a human play Thief
against it with direct keyboard input (`W`/`A`/`S`/`D`/arrows, `Space`=stay, `Q`=quit).
Pure PyTorch inference (`RecurrentRolePolicy.select_action` in
`cop_worker/rl/recurrent_policy.py`) — no LLM anywhere in this path.

Run it:
```
uv run python scripts/human_vs_rl.py --human-role thief
```
The mirror version (`--human-role cop`, agent plays cop) lives in the `vibecode-thief`
repo as `scripts/human_vs_rl.py` there, since this repo's `models/MANIFEST.json` only
tracks the cop champion (the thief repo only tracks the thief champion — that's how the
model artifacts are split across the two repos).

Both scripts already verified working end-to-end (both champion policies smoke-tested
20 turns each, no crashes) as of commit `e8af7c7`.

---

## Part 2 — New task: train cop + thief champions for a 10×10 grid

**Do not touch or overwrite the existing 7×7 champions** (`cop_recurrent_champion.pt`,
`models/MANIFEST.json`'s existing entry, `results/cop_held_out_tournament.json`). Produce
new artifacts alongside them — e.g. `cop_recurrent_champion_10x10.pt` — and add a second
manifest entry (or a separate manifest file) rather than overwriting.

### 2.1 — Same method, same script, one parameter to fix

The real training implementation is `cop_worker/rl/train_recurrent.py` (1039 lines,
in this repo) — algorithm `RecurrentA2C-GRU`, local-belief BC warm start, adversarial
curriculum (`COP_TRAINING_SCHEDULE`/`THIEF_TRAINING_SCHEDULE`), belief-supported trap
shaping. This is the exact method behind both existing champions
(`docs/RL_REPRODUCTION.md` has the reproduction command and hyperparameters for the
current cop champion: seed 20260805, hidden size 128, gamma 0.99, 11,800 cumulative
episodes). **Use the same script, same curriculum, same hyperparameters — just for a
different grid size.**

The board size is currently hardcoded as the literal `7` in 13 places in this file (not a
CLI parameter). Grep confirms the exact lines as of `e8af7c7`:
```
grep -n "\b7\b" cop_worker/rl/train_recurrent.py
```
covers: `_initial_state()` (agent spawn bounds + `grid_size=7` + scent grid init),
`_run_episode()` and `evaluate()` (both call `ScentFields.zeros(7)`,
`BeliefEngine(7, role)`, `BeliefEngine(7, opponent_role)`), and the checkpoint-saving code
in `train()`/`main()` (`obs_tensor_shape(7)` used twice — once when constructing the
network, once when saving `"input_size"` into the checkpoint dict).

The tensor-shape math itself is already grid-size-agnostic —
`cop_worker/rl/local_obs_adapter.py: obs_tensor_shape(grid_size)` correctly computes
`4*n*n + 5` for any `n`, and `local_obs_to_tensor()` reads `obs.grid_size` rather than
assuming 7. Same for the actual game physics: `cop_worker/domain/transition.py`'s
`apply_joint_action()` reads bounds from `state.grid_size` (the `DomainState` you
construct), not from any config default — so training episodes with `grid_size=10` will
run correctly once the 13 hardcoded `7`s above are changed to `10` (or, better, turned
into a `--grid-size` CLI argument so both sizes stay reproducible from the same script —
recommended, since it's a small change and keeps this script useful for any future size).

Recommend the same treatment in the thief repo — note the actual shared implementation
there lives at `vibecode-thief/agent/rl/train_recurrent.py` (also 1039 lines, same
hardcoded-7 pattern); `vibecode-thief/thief_worker/rl/train_recurrent.py` is a thin
190-line re-export wrapper around it, not a separate copy — fix the one real file, the
wrapper picks it up automatically.

### 2.2 — Known wrinkle: the "historical checkpoint" opponent

Training requires `--historical-checkpoint <path>` (a fixed prior-generation policy the
new network trains against for part of the curriculum, loaded via
`cop_worker/rl/policy_loader.py: load_checkpoint()`). For 7×7 this pointed at
`models/thief_ppo_best.pt` — an older, differently-architected PPO/DQN checkpoint (grid-
shaped conv input, not the flat vector the recurrent policy uses). For 10×10 there is no
existing checkpoint of any kind — this is a cold-start problem the original 7×7 training
run didn't have to solve (a historical checkpoint already existed by then). You'll need to
either: bootstrap a first-pass checkpoint at grid_size=10 to serve as the historical
opponent (e.g. a short imitation-only or heuristic-only run with that curriculum family
excluded via `--training-families`), or otherwise handle the missing historical family for
the first 10×10 training pass. Use your judgement — this wasn't solved as part of this
handoff, flagging it so it doesn't surprise you mid-run.

### 2.3 — Reproduction command shape (adapt grid size accordingly)

From `docs/RL_REPRODUCTION.md`, the exact invocation pattern used for the current champion
(episodes=0 here means "evaluate only" — for an actual training run set real `--episodes`,
e.g. the original used ~11,800 cumulative across multiple resumed runs):

```powershell
uv run python -m cop_worker.rl.train_recurrent `
  --role cop --episodes <N> --eval-series-per-family 30 `
  --seed 20260805 --hidden-size 128 `
  --historical-checkpoint <your-10x10-historical-checkpoint> `
  --models-dir models --evidence-dir results
```

This produces `models/cop_recurrent_champion.pt` by default (`f"{role}_recurrent_champion.pt"`
in the script) — **rename or redirect `--models-dir` so this doesn't collide with the
existing 7×7 artifact.**

### 2.4 — To actually *play* a 10×10 game afterward

`cop_worker/domain/config_validator.py`'s `GameConfig` currently **hard-rejects any
`grid_size != 7`** (`if self.grid_size != 7: errors.append(...)`) — this is a known,
already-documented discrepancy against the project's own stated standard (which lists
`grid_size>=7` as a *minimum*, not a fixed value). A separate, newer file
(`cop_worker/config/canonical_config.py`) already declares it correctly as `MINIMUM`, but
`config_validator.py` — the one actually used by gameplay — doesn't delegate to it despite
its docstring claiming it does. You'll need to loosen that check (`!=` → `<`) to actually
run a 10×10 game through the normal engine, separate from the training work above (training
itself doesn't go through `GameConfig` at all — see 2.1).

---

## Files relevant to this handoff (this repo)

- `scripts/human_vs_rl.py` — working practice-mode script, don't need to touch
- `models/cop_recurrent_champion.pt`, `models/MANIFEST.json` — existing 7×7 champion, don't overwrite
- `cop_worker/rl/train_recurrent.py` — training implementation to adapt for grid_size=10
- `docs/RL_REPRODUCTION.md` — exact hyperparameters/method reference for the existing champion
- `cop_worker/domain/config_validator.py` — the grid_size gate you'll hit once you try to play a 10×10 game
