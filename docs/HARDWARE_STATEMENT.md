# Hardware Statement — CPU-only training and gameplay

The development machine contains an NVIDIA GeForce RTX 3090, and the runtime
environment metadata that our match artifacts record (`cop_worker/game_runner_env.py`
probes `nvidia-smi`) will therefore show that GPU as *present*.

**We did not use the GPU at any point** — not for model training, not for
evaluation, and not during any friendly or counted game:

1. **No CUDA calls anywhere in the code.** The training loops
   (`cop_worker/rl/train_recurrent*`), the research trainers, and every serving
   policy contain no `.cuda()`, no `.to(device)`, and no `device=` argument;
   every tensor is created on the CPU default device. Verify with:
   `grep -rn "cuda\|\.to(device\|device=" cop_worker/rl/` — the only matches are
   `map_location="cpu"` checkpoint loads, which force CPU.
2. **The models are deliberately tiny.** The deployed policy is a
   ~200-input GRU actor-critic (hidden size 128) trained for minutes on CPU;
   the counted-game move engine is a pure-Python depth-limited minimax with no
   tensors at all on its hot path.
3. **Match-time inference is CPU-bound by design.** Measured p99 inference is
   in the low milliseconds on CPU (see `results/*_held_out_tournament.json`
   `inference_latency_ms`), far inside the wire's response window — a GPU
   would change nothing about game outcomes.

We respectfully ask that the presence of this GPU in the machine's inventory
not be weighed against the project: it is idle hardware. Everything submitted
here — training, evaluation, and all league games — reproduces on a plain
CPU-only laptop with the commands in `docs/RL_REPRODUCTION.md`.
