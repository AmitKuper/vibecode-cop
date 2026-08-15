# Hardware Statement — CPU-only training and gameplay

The development machine contains an NVIDIA GeForce RTX 3090. The signed Step-0
hardware declaration we publish records CPU, RAM, OS and Python only
(`cop_worker/step0/declaration.py`; see any `results/declaration_*.json`
`hardware_spec`), so the GPU appears nowhere in our artifacts — but the machine
does have one, and this note states plainly what was done with it.

**We did not use the GPU at any point** — not for model training, not for
evaluation, and not during any friendly or counted game:

1. **The production paths are CPU-pinned.** The recurrent trainer
   (`cop_worker/rl/train_recurrent/`) contains no `device`, `.cuda()` or
   `.to(...)` call at all, so every tensor is created on the CPU default device;
   the serving loader forces it explicitly —
   `cop_worker/rl/recurrent_loader.py` sets `device = torch.device("cpu")` and
   loads the checkpoint with `map_location=device`. The one module that would
   select CUDA if it were present, `cop_worker/rl/policy_loader.py`
   (`torch.device("cuda" if torch.cuda.is_available() else "cpu")`), loads the
   superseded DQN/PPO checkpoints and is not on the counted serving path — the
   promoted champion in `models/MANIFEST.json` is a recurrent checkpoint loaded
   through `recurrent_loader.py`.
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
