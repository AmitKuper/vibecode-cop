# QUALITY — ISO/IEC 25010 mapping (vibecode-cop)

One page: each ISO/IEC 25010 product-quality characteristic mapped to concrete,
checkable evidence in this repository. Current as of 2026-08-15.

| Characteristic | Concrete evidence in this repo |
|---|---|
| **Functional suitability** | Five counted league series completed and settled (`results/counted_series.json`): loss 35–75 vs anrbj666, then **wins of 90–30 vs imreeyal, uoh-sqak, rstabcde and najamjad**, 6/6 audits `Verified OK` each (`evidence/game_vs_*/`). Kit conformance: `verify_vectors.py` **125 checks / 15 fixtures ALL PASS** at kit `be96e57`; the CORE pheromone vectors are also ported verbatim into `tests/test_scent_chebyshev.py` so drift fails CI. |
| **Reliability** | Settlement guard: the orchestrator **withholds the league report** unless all six sub-games settled (`scripts/ref3_match/report_guard.py`, "REPORT WITHHELD"). At-least-once retries with backoff on every outbound MCP call, dedup-safe by commit (`cop_worker/net_gateway.py`, 6 retries default). Gmail pipeline: `Gatekeeper` + `TokenBucket` + `CircuitBreaker` + `DoSDetector` (`cop_worker/gmail/`). Independent **watchdog OS process** (heartbeat file, SIGTERM + technical-loss evidence on stall — `cop_worker/reliability/watchdog.py`). `DeadlineTracker`, durable IO, port-free preflight against stray processes. |
| **Performance efficiency** | Per-move search budget: iterative deepening with cost prediction under the **10 s per-call cap** (a depth is not started unless its predicted ~10x cost fits) against a 180 s live turn budget; raw depth-4 measured up to ~74 s in the open midgame, the budgeted engine's worst live move ≈ 7 s (`cop_worker/rl/pursuit_search.py`, DESIGN AD-6). Territory eval costs two 49-cell BFS maps per leaf — measured affordable. |
| **Compatibility / interoperability** | Reference-v3 wire proven against two independent implementations plus the unmodified kit's sparring peer (`scripts/verify_reference_v3_interop.py`). Unknown-peer MCP interfaces handled by the protocol-introspection pipeline (`cop_worker/protocol/`: `transport_probe → introspector → schema_mapper → mapping_plan → adapter/profile → verifier`). |
| **Usability** | Live GUI (`cop_worker/gui/app.py` + `live_view_model.py`); replay tooling (`scripts/replay_viewer.py`); workspace `game-status` skill parses match logs into a human status report; `docs/counted_game_checklist.md` + `docs/MATCH_DIAGNOSIS_PLAYBOOK.md` turn log signatures into operator instructions. |
| **Security** | CI secret scan (credential-shaped regexes over `*.py`/`*.json`). League address stored **nowhere** — enforced by `tests/test_config_single_source.py::test_runtime_toml_has_no_league_address`; own-inbox hardcoded default recipient (`cop_worker/gmail/gatekeeper.py`, DESIGN AD-7). Commit-reveal + mutual audit as the wire trust model. Threat model: `docs/SECURITY_THREAT_MODEL.md`. `secrets/` gitignored; `.env.example` carries placeholders only. |
| **Maintainability** | Byte-identical `league_manager` copies collapsed into module aliases (`league_manager/gmail/*.py`, `protocol/dsl.py`, … — `sys.modules[__name__] = sys.modules["cop_worker…"]`) with one canonical implementation; remaining copies drift-guarded by mirrored `_lm` test suites (DESIGN AD-9). Ruff lint + format clean and CI-gated; docstring-first culture (regression tests document their live incident). Architecture authority: `docs/DESIGN.md`; testing strategy: `docs/TESTING.md`. |
| **Portability** | `uv` + committed `uv.lock`, CI runs `uv sync --frozen` + `uv lock --check` on ubuntu while development and all five counted games ran on Windows 11 — the same lockfile serves both. Per-OS install/run instructions in `README.md`; no OS-specific paths in library code. |

## Extension points

- **New opponent** — add `config/opponents/<name>/` (`game.json` + `runtime.toml`),
  launch with `--config <name>`; the effective config is saved back to the profile
  after each match. No code changes.
- **New scent model** — register the kit-recomputed lock hash in `SCENT_LOCKS`
  (`cop_worker/protocol/reference_v3/constants.py`), implement the emission (as
  `scent_chebyshev.py` did), and stamp promoted checkpoints with the matching
  `obs_mode` in `models/MANIFEST.json`; the load-time guard enforces the pairing.
- **New movement policy** — implement the two-method seam the serving loop
  depends on: `select_action(observation, belief, legal) -> action` and `reset()`
  (see `cop_worker/rl/counted_policy.py`, `search_policy.py`); select with
  `--move-policy {rl,hybrid_search,hybrid_search_belief}`.
- **New protocol dialect** — the introspection pipeline
  (`cop_worker/protocol/introspector.py` → `schema_mapper.py` → `mapping_plan.py` →
  `profile.py`/`adapter.py`, verified by `verifier.py`) maps an unknown compatible
  MCP interface onto the canonical protocol before play.

## Thread-safety note

Concurrency inside each process is **asyncio on a single event loop** — wire I/O
interleaves by await, not by threads, so match state needs no locking. The narrow
places where real threads touch shared state hold explicit locks:
`threading.Lock` in `LiveViewModel` (GUI thread vs runner), in the MCP
`session_registry` (per-session locks for concurrent inbound calls), and inside the
Gmail `TokenBucket`/`CircuitBreaker`/`Sender`. Token buckets (Gmail and
`net_gateway`) are **per-process** and are not coordinated across processes. That is
safe under the split architecture because the two role workers each own their own
endpoint and their own outbound calls, while the league report is sent by the
orchestrator alone — no two processes share a bucket's subject. The port preflight
(`ref3_match/net.py::_check_port`) still refuses to start if 61223/61224 are already
bound, so a second series cannot race the first.
