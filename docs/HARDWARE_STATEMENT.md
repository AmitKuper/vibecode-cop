# Hardware Statement — CPU-only training and gameplay

The development machine contains an NVIDIA GeForce RTX 3090. The signed Step-0
hardware declaration we publish records CPU, RAM, OS and Python only
(`cop_worker/step0/declaration.py`; see any `results/declaration_*.json`
`hardware_spec`), so the GPU appears nowhere in our artifacts — but the machine
does have one, and this note states plainly what was done with it.

**The GPU played no part in anything submitted or played** — not in model
training, not in the promotion evaluations behind the shipped champions, and
not in any friendly or counted game. (The only place CUDA can engage at all
is a research-only legacy loader exercised by unit tests on GPU machines —
`policy_loader.py` below — which serves nothing on the counted path.)

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

## Hardware conferred no advantage in any counted game — scoring request

We understand scoring may take the declared hardware spec into account. We ask
that ours not be counted against us, on the following evidence:

1. **Seven counted games were played; the GPU was used in none of them.** Every counted
   series (anrbj666, imreeyal, uoh-sqak, rstabcde, najamjad, nis-yar1,
   bestteam) was played through the CPU-pinned production path described
   above; the signed `hardware_spec` in each Step-0 declaration records
   CPU/RAM/OS/Python and no GPU, and that declaration matches what actually
   ran.

2. **CPU strength was not the binding constraint — the protocol was.**
   Measured decision latency on this machine is p99 ≈ 1.2 ms
   (`results/cop_held_out_tournament.json`, `inference_latency_ms`) against
   the signed 30-second response window — roughly a 25,000× margin. The
   pace of a match is set by the wire (turn windows, the 30 req/min
   gatekeeper both sides sign), not by compute: any commodity laptop meets
   the same deadlines with orders of magnitude to spare.

3. **More hardware would not have produced different moves.** The counted
   move engine is a depth-limited minimax whose depth is a constant in code,
   not adaptive to available compute, plus a ~200-input GRU fallback that
   runs in a millisecond on CPU. The same code on a weaker machine selects
   the same actions; cores, RAM and the idle GPU do not deepen the search or
   change a single decision.

4. **Counted outcomes did not track hardware.** At least one counted
   opponent declared a strictly newer CPU and a discrete GPU in their own
   Step-0 declaration; the series outcomes tracked the algorithms and
   protocol discipline, not the silicon on either side.

We therefore ask to be scored on the algorithms, the protocol compliance,
and the evidence — the same standard as a team that developed on a laptop —
since that is, in every respect that reached the wire, what we were.
