# Codex Stage-A Baseline Audit

Date: 2026-08-05 (Asia/Jerusalem)

Scope: `vibecode-cop` at `bc8de6add8a979fa915295c71e47d2773ff244d2`
and `vibecode-thief` at `b7a65401b64ea9fa7e48dfda83cae6d9ecc4ef61`.
Both trees were clean before this audit. Repository reports were treated as
hypotheses; statuses below come from direct source inspection and commands.

## Outcome

Baseline score: **36/100 — FAIL**.

| Dimension | Score | Status | Main evidence |
|---|---:|---|---|
| Binding compliance | 42 | FAIL | Nonce disclosed in ordinary reveal; counted root bypass; split physics; incomplete Step-0/audit/result path. |
| Production correctness/reliability | 28 | FAIL | CLI is not counted; critical construction, adaptive, Watchdog, ledger, and Gmail failures are warnings. |
| Competitive strategy | 15 | FAIL | Release models are ignored local files and counted play uses a heuristic when `rl_model_loaded` is false. |
| Adaptive MCP | 45 | FAIL | Declarative unit fixtures exist, but live negotiation falls open to native identity and adapter use is incomplete. |
| Documentation/submission evidence | 50 | FAIL | Existing reports overclaim; verifier accepts SKIP and ignored local artifacts; thief verifier is absent. |

No numeric 100 claim is valid. The 55-rule status is in
`docs/REQUIREMENTS_TRACEABILITY.md`.

## Reproducible baseline

| Command | Cop result | Thief result |
|---|---|---|
| `git rev-parse HEAD` | `bc8de6a...` | `b7a6540...` |
| `git status --short` | clean | clean |
| `uv --version` | 0.11.19 | 0.11.19 |
| `uv run python --version` | 3.13.14 | 3.13.14 |
| `uv sync --frozen` | PASS; pre-existing Torch RECORD warning | PASS; same warning |
| `uv lock --check` | PASS, 230 packages | PASS, 230 packages |
| `uv run pytest -q` | 1308 pass, 133.65 s | 1181 pass, 2 skip, 132.94 s: FAIL |
| branch pytest with `--cov-branch --cov-fail-under=85` | rounded 85%, but invalid broad mandatory omissions | 80.76%, FAIL |
| `uv run ruff check .` | PASS | PASS |
| `uv run ruff format --check .` | FAIL, 15 files | FAIL, 9 files |
| `uv run python -m <role> --help` | FAIL: opens `--help` as config | same FAIL |
| tracked secret-pattern scan | no matches | no matches |
| readiness verifier `--skip-slow` | exits 0 with 2 SKIP and 3 mislabeled external code gates | file absent |

The configured coverage result is not an acceptance PASS: both pyprojects omit
mandatory RL training/evaluation/league and Gmail/report modules. The thief's two
executed skips are missing compatible model preconditions. Other conditional
skips are present for Torch, CrewAI, counted preconditions, and config paths.

Historical tags exist, but `v4.0-v8-complete` points to cop `9af09eb...` and thief
`f665e9c...`, not the audited HEADs. Final release tags remain
`EXTERNAL_PENDING` until the code/model/evidence freeze and push.

## Counted production path inspection

The role `__main__.py` entry points construct `PeerAgentRuntime` as an MCP server
without an explicit `RuntimeMode`. `PeerAgentRuntime` constructs `PeerRuntime`
with its default `counted_mode=False`. In `PeerRuntime.run_game`, counted
`AgentOrchestrator` creation receives no required config, its exception is caught,
and gameplay continues. The CLI therefore does not provide the binding chain.

Additional directly reproduced defects:

- `_validate_counted_preconditions()` uses invalid
  `subprocess.check_output(..., capture_output=True).stdout` code and runs the Git
  check only behind an optional flag.
- `_init_protocol_adapter()` catches every error and installs a native identity
  profile, including counted mode.
- `run_peer_turn()` selects the heuristic whenever `rl_model_loaded` is false,
  including intended counted execution.
- The ordinary reveal payload contains the nonce. Appendix E Rule 18 and Chapter
  5 require nonce secrecy until final audit.
- Illegal peer moves are changed to `STAY`; a protocol violation must be an
  explicit technical outcome.
- Movement uses legacy `RulesEngine.apply_moves`, placement uses
  `apply_joint_action`, and passive placement uses `apply_place_action`.
- Passive initialization does not create a symmetric counted orchestrator or
  exchange signed complete Step-0 declarations.
- Final-audit code creates a new Ed25519 key pair at audit time, accepts a missing
  peer summary, and does not bind the key to Step-0.
- `verify_bilateral_consensus()` exists but no live code builds/exchanges signed
  byte-identical `ResultAgreement` objects.
- Watchdog startup errors, ledger errors, Gmail errors, and game-end notification
  errors are warnings in counted mode.
- `GameSeries` is explicitly an in-process central simulator and catches gamelet
  errors; it is not the required P2P counted production route.

## Model and tournament evidence

Both workspaces contain ignored `models/` directories. `git status --ignored`
reports `!! models/`, so `MANIFEST.json`, `cop_ppo.pt`, and `thief_ppo.pt` are not
available from a clean clone. The verifier reads these ignored files and reports
PASS. Existing CSVs and model reports are static repository claims, not an
executable held-out promotion gate. Counted production has no clean-clone model
precondition proof and silently substitutes a heuristic.

## Adaptive MCP evidence

The adapter, typed mapping, verifier, probes, fixtures, and profile cache have
substantial unit coverage. This is useful infrastructure, not production proof.
The live path strips/rewrites the URL, catches negotiation failure, installs an
identity profile, and then the regular MCP client remains the direct gameplay
transport. The verifier marks the real two-process and six-gamelet fixture work
`EXTERNAL_PENDING`, but they are locally code-verifiable and must be FAIL until
implemented.

## Prior-review finding classification

| # | Prior finding | Classification at audited HEAD | Evidence |
|---:|---|---|---|
| 1 | Invalid Git SHA subprocess call | STILL PRESENT | `AgentOrchestrator._validate_counted_preconditions`. |
| 2 | Incomplete counted Orchestrator / fail-open legacy | STILL PRESENT | Missing config, caught exception, implicit development default. |
| 3 | Passive thief not symmetrically initialized | STILL PRESENT | `init_passive_game()` creates board/rules only. |
| 4 | Adapter interface mismatch disables adaptation | PARTLY CHANGED, EFFECT STILL PRESENT | New adapter API exists; live failure still falls open and gameplay bypasses deterministic execution. |
| 5 | Adaptive failure accepts identity/native | STILL PRESENT | `_init_protocol_adapter()` unconditional catch/fallback. |
| 6 | Canonical transition not sole authority | STILL PRESENT | Three active/passive physics paths. |
| 7 | RL input obsolete / heuristic replaces policy | STILL PRESENT IN EFFECT | Local adapter exists, but counted path does not load/require champion and uses heuristic. |
| 8 | Models not clean-clone reproducible | STILL PRESENT | Entire `models/` directory ignored. |
| 9 | Unsalted enumerable private state hash | STILL PRESENT / NEEDS REMOVAL | `hash_game_state(board_state)` covers small board state used in commitment path. |
| 10 | Audit keys self-supplied / result not Step-0-bound | STILL PRESENT | New keys in both audit helpers; no live result consensus. |
| 11 | Full signed bilateral Step-0 types not live-exchanged | STILL PRESENT | StartGame sends legacy message fields only. |
| 12 | Gmail and ledger fail open | STILL PRESENT | broad `except` warnings in counted terminal path. |
| 13 | Verifier accepts SKIP/existence checks | STILL PRESENT | `all_code_verifiable_pass()` accepts SKIP; shallow gates; real local gates mislabeled external. |
| 14 | Coverage omits RL/Gmail | STILL PRESENT | explicit broad `tool.coverage.run.omit`. |
| 15 | Version/report/tag inconsistency | STILL PRESENT | tags do not identify HEAD; reports claim readiness despite failures. |

New high-impact findings are early nonce disclosure, peer-error-to-`STAY`, missing
CLI help/mode contract, thief coverage failure, and absence of the verifier in the
thief repository.

## External-only evidence

Public tunnel play, two outside groups, real independent Gmail sends and message
IDs, real group ID, unchanged-layout Moodle PDF, individual submissions, real-match
screenshots, and pushing the final annotated tags are `EXTERNAL_PENDING`. Local
subprocess, transport fixture, tournament, fake-Gmail, model, replay, Watchdog,
secret, coverage, and documentation gates are code-verifiable and are not external.
