# Codex 100-Readiness ExecPlan

This is the active living plan for the distributed cop/thief product. It follows
the format in `../.agent/PLANS.md` at the workspace root and must be updated when
evidence, design decisions, or milestone status changes.

## Purpose and user-visible outcome

A successful release starts each role from its real CLI in `RuntimeMode.COUNTED`,
fails closed before any commitment if a protected dependency is unavailable,
negotiates and locks a compatible peer protocol, and completes exactly six
gamelets between independent processes. Every turn uses only local observations,
a Bayesian belief, recurrent role-specific RL inference, a legal-action mask, and
the one canonical physical transition. The series finishes only after bilateral
audit and byte-identical signed result agreement, durable league accounting, two
independent Gatekeeper-authorized Gmail reports, and replay trust-anchor output.

Code-verifiable work ends with all acceptance gates passing in both clean
repositories. Public tunnels, external opponents, real Gmail delivery, group ID,
Moodle artifacts, screenshots from real matches, pushed release tags, and other
genuine real-world evidence remain `EXTERNAL_PENDING` until actually produced.

## Baseline

Captured 2026-08-05T01:15:52+03:00 before source changes.

| Item | Cop | Thief |
|---|---|---|
| Starting HEAD | `bc8de6add8a979fa915295c71e47d2773ff244d2` | `b7a65401b64ea9fa7e48dfda83cae6d9ecc4ef61` |
| Initial tree | clean | clean |
| Package version | 3.0.0 | 3.0.0 |
| Python under uv | 3.13.14 | 3.13.14 |
| uv | 0.11.19 | 0.11.19 |
| Torch | 2.13.0+cpu, optional/local | 2.13.0+cpu, optional/local |
| `uv sync --frozen` | PASS, warning about pre-existing Torch RECORD | PASS, same warning |
| `uv lock --check` | PASS, 230 packages | PASS, 230 packages |
| Full pytest | PASS, 1308 in 133.65 s | FAIL, 1181 pass + 2 skips in 132.94 s |
| Configured branch coverage | PASS but broad mandatory omissions, rounded 85% | FAIL, 80.76% |
| Ruff lint | PASS | PASS |
| Ruff format | FAIL, 15 files | FAIL, 9 files |
| Clean CLI `--help` | FAIL, interpreted as a config filename | FAIL, interpreted as a config filename |
| Readiness verifier | false-positive: SKIP and ignored local models accepted | absent |

Initial tags are `v1.0-submission`, `v2.0-submission`, `v3.0-code-ready`, and
`v4.0-v8-complete`. None points at the starting HEAD, so no tag is release proof.
Ignored `models/` directories contain local artifacts, but the champions and
manifest are absent from the tracked clean-clone product.

Baseline score: **36/100**, not release-ready.

| Dimension | Score | Reproducible reason |
|---|---:|---|
| Binding compliance | 42/100 | Several domain/config primitives pass, but the counted lifecycle violates nonce secrecy, production-path authority, and bilateral finalization. |
| Production correctness/reliability | 28/100 | Live CLI is not counted; critical construction/adapter/Watchdog/ledger/Gmail failures are swallowed; no real six-gamelet production proof. |
| Competitive strategy | 15/100 | Models are ignored local files, counted mode falls back to heuristic, and held-out promotion evidence is not executable. |
| Adaptive MCP interoperability | 45/100 | Declarative components and unit fixtures exist, but live failure falls open to a native profile and gameplay does not consistently use the deterministic adapter. |
| Documentation/submission evidence | 50/100 | Many documents exist, but current claims conflict with runtime evidence and the executable verifier is incomplete. |

See `CODEX_BASELINE_AUDIT.md` and `docs/REQUIREMENTS_TRACEABILITY.md` for the
evidence-backed finding classification and all 55 rules.

## Authoritative requirements

The controlling sources are:

1. `context/police_thief_p2p_english.md`, Appendix E rules 1-55.
2. Appendix F for all fixed, minimum, and negotiated quantities. In particular:
   two agents, orthogonal plus stand movement, scent 0.9/0.10/5x5, fixed scoring,
   exactly six gamelets, diversity 10, two minimum opponents, ten maximum counted
   matches, and the lecturer report address are fixed; board/steps/barriers and
   Gatekeeper limits are minimums; origin, starts, language bounds, timeouts, and
   LLM token estimate are negotiated.
3. `context/guidelines.md` for professional documentation, uv, TDD, branch
   coverage >=85%, zero Ruff violations, analysis, UI/UX, cost, security, and
   release evidence.
4. The frozen acceptance, competitive-strength, and adaptive-MCP contracts.

Mandatory items must execute on the counted production path. Forbidden behavior
must fail closed. Recommended Rule 25 is strengthened by this project's explicit
choice of RL as its required primary counted movement policy. Any source conflict
is recorded in `docs/KNOWN_DEVIATIONS.md`.

## Architecture and invariants

The target composition root is the role CLI, which parses an explicit runtime
mode and constructs exactly one `AgentOrchestrator`. In counted mode that root
owns the role key for the full series, Step-0 declarations, a single
`ProtocolCoordinator`, adaptive profile, policy, observation/belief history,
Watchdog/deadlines/recovery, journals, result consensus, ledger, live view,
replay anchor, and Gatekeeper. It delegates transport but no subsystem bypasses
its lifecycle authority.

Cop and thief use distinct OS processes, configurations, ports, work directories,
logs, secrets, signing keys, and memories. They share no runtime files. There is
no central judge or in-process counted simulator.

`apply_joint_action()` is the only physical transition for movement and barrier
actions on both active and passive peers. Every counted boundary validates the
fixed six-gamelet series and fixed/minimum parameter semantics.

The protocol state machine is signed bilateral Step-0 -> locked profile -> for
each step commit -> acknowledge -> reveal without nonce -> verify/apply -> final
audit with nonces -> bilateral audit summaries -> byte-identical signed result
agreement -> ledger -> independent report -> DONE. Illegal transitions and peer
violations produce explicit technical outcomes; no peer error is converted to
`STAY`.

Actor inputs are `LocalObservation`, Bayesian `BeliefState`, and recurrent
history only. Hidden current opponent coordinates are forbidden from actor,
language prompts, serialized observation, and live GUI. Counted inference loads
a checksum-verified role champion, masks illegal actions before selection, and
never uses a heuristic fallback.

Adaptive MCP is pre-game only: bounded transport probe -> complete introspection
-> understanding agent -> typed mapping -> static verification -> placeholder
conformance probes -> signed/hashed locked profile. Protected values are injected
and verified by deterministic code. Schema changes or incompatibility abort
before commitment; gameplay makes zero protocol-agent/LLM calls.

## Milestones

### M0 — Independent baseline and traceability

Problem: prior reports and verifier results are not production proof. Inspect all
entry points and direct dependencies, reproduce the gates, and freeze an honest
baseline. Acceptance is this plan, audit, ledger, and 55-rule matrix with exact
commands and both starting SHAs. Evidence: baseline command outputs summarized in
the referenced documents. Risk: no production source change. Rollback: revert
documentation-only edits. Resulting SHAs: pending commit.

### M1 — One fail-closed counted composition root

Inspect role `__main__.py`, `peer_agent_runtime.py`, `peer_runtime.py`,
`game_series.py`, Step-0 types, and coordinator. Add an explicit CLI contract,
complete counted dependency configuration, symmetric active/passive startup, and
exactly-six enforcement at CLI/service/domain boundaries. Acceptance: clean
subprocess startup plus a real two-process one-gamelet warm-up and counted
six-gamelet trace containing every mandatory component. Risk: existing development
entry behavior; preserve it only behind explicit development mode. SHAs: pending.

### M2 — Zero-trust turn, audit, result, and reporting lifecycle

Inspect turn helpers, server handlers, canonical transition, journals, signing,
audit/result types, Watchdog, ledger, Gmail, safe view, and replay. Remove early
nonce disclosure, implicit `STAY`, split physics, ephemeral audit keys, optional
consensus, and swallowed counted failures. Acceptance: tamper/retry/chaos/fake
Gmail tests plus byte-identical bilateral result and replay anchor from the real
two-process run. Risk: wire compatibility; version schemas explicitly. SHAs:
pending.

### M3 — Counted RL champions and strength gate

Inspect observation adapters, recurrent networks, loaders, action spaces, training,
self-play, league, evaluation, manifests, and result datasets. Track immutable
role champions and checksums, make clean-clone load deterministic, wire them before
Step-0, and prohibit fallback. Run held-out six-gamelet tournaments against all
required families/seeds, bootstrap confidence intervals, latency percentiles,
technical/illegal rates, ablations, sensitivity, learning curves, and the declared
promotion criterion. Risk: compute cost; prefer reproducible CPU-sized champions
and preserve provenance. SHAs: pending.

### M4 — Adaptive MCP compatibility matrix

Inspect probes, introspector, agent, mapping verifier, adapters, profile cache, and
transport ports. Prove streamable HTTP, SSE, and stdio fixtures; compatible renamed,
split, nested, packed, enum, response, and optional variants complete six gamelets;
incompatible nonce/audit/canonicalization/binding/order/injection variants fail
before commit. Risk: real FastMCP API variance; pin and test actual transport.
SHAs: pending.

### M5 — Professional quality and executable verifier

Remove broad mandatory coverage omissions and conditional mandatory skips. Add
branch tests until both repositories exceed 85%; format and lint all tracked code;
verify frozen locks, clean startup, cross-repo conformance, secrets, and docs.
Replace existence/import gates with subprocess/runtime evidence and make every
code-verifiable SKIP fail. Acceptance is one verifier exit 0 in each clean tree
with machine-readable per-dimension results. Risk: verifier self-reference; each
gate records command, exit code, artifact hash, and mock policy. SHAs: pending.

### M6 — Final release evidence

Regenerate final reports, external checklist, release manifest, and score JSON from
the exact final SHAs/models. All code-verifiable statuses must be PASS. Genuine
public-tunnel/opponent/Gmail/group-ID/Moodle/screenshot/pushed-tag tasks remain
EXTERNAL_PENDING. Risk: never synthesize evidence. SHAs: pending.

## Progress

- [x] 2026-08-05T00:57+03:00 — recorded both exact starting SHAs and clean trees.
- [x] 2026-08-05T01:03+03:00 — read the complete authoritative book, Appendix E/F,
  guidelines, context contracts, and planning rules.
- [x] 2026-08-05T01:15+03:00 — ran frozen sync, lock, test, branch coverage, Ruff,
  startup, tag, model-tracking, and verifier baseline checks.
- [x] 2026-08-05T01:20+03:00 — classified the production-path defects and froze M0
  documents.
- [x] 2026-08-05T02:10+03:00 — implemented explicit counted CLIs, strict six-gamelet
  boundaries, bilateral signed Step-0 identity locking, canonical active/passive
  transitions, nonce-safe audit, and signed bilateral result agreement; focused
  composition/zero-trust/result tests pass in both repositories. Real subprocess
  acceptance remains open.
- [x] 2026-08-05T02:25+03:00 — wired deterministic protected-field MCP mappings into
  live gameplay and proved compatible mapping/unit fixtures; real transport and
  incompatible pre-commit fixture matrices remain open.
- [x] 2026-08-05T02:44+03:00 — corrected canonical x/y scent and belief geometry and
  Appendix-F center intensity, then calibrated local-only demonstration-guided
  recurrent A2C at 91.25% overall, 70% worst-family, zero technical failures, and
  1.66 ms average inference/environment latency over 80 held-out games. The
  calibration artifact is not a champion; immutable role artifacts and the full
  tournament gate remain open.
- [x] 2026-08-05T03:20+03:00 — trained and evaluated frozen role candidates over
  150 exact six-gamelet held-out series per role. Cop passed preliminary strength
  evidence (88.56% gamelets, 100% series, 78.89% worst family). Thief remained
  unpromoted: low-temperature candidate scored 64.22% gamelets and 16.11% worst
  family but 7,390 official points versus the Bayesian heuristic's 7,395. The
  evaluator now predeclares and enforces a paired-bootstrap official-score gate,
  nonzero families, zero technical failures, and p99 inference below 30 ms.
- [ ] M1 counted composition root.
- [ ] M2 zero-trust final lifecycle.
- [ ] M3 RL strength.
- [ ] M4 adaptive MCP.
- [ ] M5 complete quality/verifier gates.
- [ ] M6 final release evidence.

## Decisions

- Treat any caught counted-mode dependency failure as a technical abort, never a
  warning/fallback.
- Keep one durable Ed25519 identity per process/series and bind Step-0, audit, and
  result signatures to it; no self-supplied final-audit keys.
- Reveal nonce values only in final audit, interpreting Appendix E Rule 18 and the
  explicit Chapter 5 phase text as controlling.
- Use `apply_joint_action()` for every physical action on both peers.
- Track release champion artifacts despite generic model-output ignore rules; use
  narrow ignore exceptions for the manifest and selected champions.
- Treat coverage of mandatory RL, Gmail, adaptive, and lifecycle modules as
  required even where the previous pyproject omitted them.

## Discoveries and surprises

- `AgentOrchestrator` counted construction is called without its required config;
  the exception is logged and gameplay continues without the composition root.
- The Git SHA check uses an invalid `check_output(..., capture_output=True).stdout`
  pattern and is disabled unless an optional flag is set.
- Adaptive negotiation always falls back to a native identity profile, including
  counted mode.
- The turn loop sends `nonce` during ordinary reveal, contrary to the binding rule.
- Peer protocol/legality violations are silently converted to `STAY`.
- Only barrier actions use the canonical transition; movement uses legacy physics,
  and the passive barrier path uses another helper.
- Passive startup does not symmetrically construct the counted Orchestrator or
  exchange a complete signed Step-0 declaration.
- Audit peers generate new signing keys during final audit and accept an absent
  peer summary. No production `ResultAgreement` exchange exists.
- Watchdog, league, and Gmail errors are warnings in counted mode.
- Local ignored models make the cop verifier pass gates that fail in a clean clone.
- `all_code_verifiable_pass()` accepts `SKIP`, and real two-process/tournament work
  is mislabeled external although it is locally code-verifiable.
- The thief has no verifier/result JSON and fails configured branch coverage.
- Asymmetric coordinates exposed transposed scent/belief grids, and the symmetric
  legacy tests had concealed the error. The Appendix-F center emission was also
  1.0 instead of fixed 0.9.
- Sparse-reward recurrent A2C collapsed and plain online expert regularization
  omitted decisive barrier actions. A local-only behavioral-cloning warm start
  followed by recurrent A2C removed that failure in calibration without exposing
  hidden coordinates to inference.
- The first privacy-correct thief candidate matched but did not beat the strongest
  Bayesian heuristic on identical held-out seeds. Aggregate win rate alone is not
  promotion evidence; the checkpoint remains a rejected candidate until the
  machine-enforced bootstrap score gate passes.

## Validation

Exact baseline commands and results are recorded in `CODEX_BASELINE_AUDIT.md`.
Every later command, exit code, duration, artifact, and rerun trigger is appended
to `docs/PROGRAM_EXECUTION_LEDGER.md`. A later PASS replaces a baseline FAIL only
when the counted production composition root and an end-to-end test provide the
evidence.

## Final traceability

`docs/REQUIREMENTS_TRACEABILITY.md` is the live 55-row rule map. Each
code-verifiable final PASS must name a production symbol, an exact test, and a
runtime evidence artifact. External-only rows must remain `EXTERNAL_PENDING`.
