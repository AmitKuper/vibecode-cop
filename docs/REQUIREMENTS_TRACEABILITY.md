# Appendix-E Requirements Traceability — Stage-A Baseline

Evidence date: 2026-08-05. Status vocabulary is restricted to `PASS`, `FAIL`, and
`EXTERNAL_PENDING`. A class/import/unit test is not enough: a code-verifiable rule
is PASS only when the counted production composition invokes it and an end-to-end
test proves it. Appendix F controls every quantitative value.

| # | Binding rule | Class | Production/test/runtime evidence | Baseline status |
|---:|---|---|---|---|
| 1 | Police and thief are separate processes | Mandatory | Role servers can run separately, but neither CLI enters a proven counted six-gamelet route; current two-process tests do not prove the required CLI lifecycle. | FAIL |
| 2 | No shared memory/variables | Forbidden | Counted path is absent and the alternative `GameSeries` is explicitly in-process/central; no real counted isolation artifact. | FAIL |
| 3 | Orchestrator is the single subsystem entry | Mandatory | `PeerRuntime.run_game()` catches failed `AgentOrchestrator` construction and continues; CLI constructs `PeerAgentRuntime` directly. | FAIL |
| 4 | Proper game state machine | Mandatory | `agent/mcp/coordinator.py::ProtocolCoordinator`; transition suites including `tests/test_protocol_state_machine.py`. | PASS |
| 5 | Reject illegal state transitions | Mandatory | Coordinator guards in `agent/mcp/server_handlers.py`; adversarial/order tests pass. | PASS |
| 6 | Deadline tracking prevents deadlock | Mandatory | `DeadlineTracker` exists, but production turn waits use a different timeout and the counted Orchestrator may be absent; no counted deadline trace. | FAIL |
| 7 | Independent Watchdog/recovery | Mandatory | Watchdog exists, but Orchestrator may be absent and startup failure is only a warning. | FAIL |
| 8 | Live GUI shows local truth only | Mandatory | `SafeLiveView` filters fields, but live publishing is conditional on the bypassed Orchestrator; no counted GUI trace. | FAIL |
| 9 | Never show objective board | Forbidden | Unit leak tests pass, but counted CLI/GUI production evidence is absent. | FAIL |
| 10 | Public tunnel exposure | Mandatory | Runbook only; genuine public endpoint/match must be produced externally. | EXTERNAL_PENDING |
| 11 | Byte-identical shared config | Mandatory | Raw `config_sha256` checked by `handle_start_game`; mismatch tests in config/transport suites. | PASS |
| 12 | Minimums only increase by agreement | Mandatory | `agent/config/canonical_config.py` field kinds and config conformance tests enforce Appendix-F fixed/minimum semantics. | PASS |
| 13 | Orthogonal or stand movement only | Mandatory | Canonical domain enforces it, but ordinary production movement bypasses the canonical transition. | FAIL |
| 14 | No diagonal movement | Forbidden | Same production bypass as Rule 13; no one-authority counted proof. | FAIL |
| 15 | Declare every barrier placement openly | Mandatory | `PLACE_*` is the committed/revealed action and placement tests cover disclosure. | PASS |
| 16 | Never lie about barrier location | Forbidden | Barrier target is derived deterministically from disclosed action and position; no independent location field can differ. | PASS |
| 17 | SHA-256 Commit-Reveal | Mandatory | `agent/mcp/crypto.py::create_commitment`; commit/audit tests pass and live turn invokes it. | PASS |
| 18 | Nonce secret until final audit | Mandatory | `run_peer_turn()` includes `nonce` in ordinary reveal payload. | FAIL |
| 19 | Audit mismatch causes technical loss | Mandatory | `do_final_audit()` overrides outcome on mismatch; adversarial commitment tests pass. | PASS |
| 20 | Replay reconstruction and verification | Mandatory | Replay classes/tests exist, but production emits no agreed signed result trust anchor; no counted replay artifact. | FAIL |
| 21 | Truthfully declare capture | Mandatory | Capture derives from board/domain state rather than peer assertion; outcome tests pass. | PASS |
| 22 | Reject false capture | Forbidden | Domain/rules engine requires geometric capture/trap; adversarial tests pass. | PASS |
| 23 | Lock scent model before game | Mandatory | Hash fields exist, but complete signed Step-0 declarations are not bilaterally exchanged in live handshake. | FAIL |
| 24 | Signed hardware declaration before game | Mandatory | Declaration types/builders exist, but live start message does not carry/verify bilateral signed declarations. | FAIL |
| 25 | Keep LLM from movement; project uses RL primary | Recommended + project mandatory | Counted-intended turn uses heuristic whenever `rl_model_loaded` is false; champions are ignored local files. | FAIL |
| 26 | Free natural language | Mandatory | `NaturalLanguagePolicy` is invoked in active/passive turns; language tests pass. | PASS |
| 27 | No numeric-location verbal protocol | Forbidden | Natural-language templates and numeric-location guard have direct tests. | PASS |
| 28 | Gmail token bucket | Mandatory | `agent/gmail/token_bucket.py`, integrated Gatekeeper, fake-service tests. | PASS |
| 29 | Gmail DOS detector | Mandatory | `agent/gmail/dos_detector.py` and circuit breaker are in Gatekeeper; tests pass. | PASS |
| 30 | Send-only Gmail authorization | Mandatory | Gmail setup/runtime code specifies `gmail.send`; no broader scope found. Real auth remains external but code contract passes. | PASS |
| 31 | Minimum outside groups | Mandatory | Requires at least two real different groups and cannot be fabricated. | EXTERNAL_PENDING |
| 32 | Automatic result report via Gmail API | Mandatory | Counted send is conditional on an Orchestrator that may be absent and send failure is swallowed; code side not ready. Real delivery also remains external. | FAIL |
| 33 | Final report is valid signed JSON | Mandatory | Live code sends a small unsigned `result` dict, not the bilateral signed `ResultAgreement`/required report schema. | FAIL |
| 34 | No free-text final report | Forbidden | `Gatekeeper._validate_body()` rejects non-JSON-looking body; fake-Gmail test passes. | PASS |
| 35 | Identical bilateral result; each peer reports | Mandatory | `verify_bilateral_consensus()` is unused; no production result exchange. | FAIL |
| 36 | Comprehensive mutual audit | Mandatory | Summary keys are generated during audit, not Step-0-bound; peer summary is optional and parse failure does not necessarily fail. | FAIL |
| 37 | Accurate prior counted-match declaration | Mandatory | Field/ledger exist, but full signed declarations are not exchanged/verified. | FAIL |
| 38 | False match count disqualifies | Forbidden | No bilateral signed declaration verification in production; ledger errors are swallowed. | FAIL |
| 39 | Never commit secrets | Forbidden | Tracked secret-pattern scan found no key material. | PASS |
| 40 | Credential files in `.gitignore` | Mandatory | Credential/token patterns are explicitly ignored in both repositories. | PASS |
| 41 | Documented final Git tag | Mandatory | Historical tags do not identify audited HEAD; final tag/push waits for actual freeze. | EXTERNAL_PENDING |
| 42 | Comprehensive accurate academic README | Mandatory | README exists but readiness/model/production claims conflict with this executable baseline. | FAIL |
| 43 | Moodle PDF unchanged layout | Mandatory | Requires official external form and submission. | EXTERNAL_PENDING |
| 44 | Each member submits separately | Mandatory | Human external action. | EXTERNAL_PENDING |
| 45 | Real unique eight-character group ID | Mandatory | Validator exists; actual course identity not available and must not be invented. | EXTERNAL_PENDING |
| 46 | Barrier placed on thief captures | Mandatory | Canonical transition supports it, but passive production uses a separate helper and movement path is split. | FAIL |
| 47 | Trapped thief is caught | Mandatory | Domain/rules semantics and exact trapped-thief tests pass. | PASS |
| 48 | Fixed scoring table | Mandatory | Canonical config fixes 20/5 and 5/10 plus tie 2; scoring tests pass. | PASS |
| 49 | Two repositories with cross-links | Mandatory | Both repositories exist and README line 3 links the companion. | PASS |
| 50 | README/config/PRD/PLAN/TODO in each repo | Mandatory | Required artifact classes are present in both tracked trees. | PASS |
| 51 | Lecturer agent report address | Mandatory | Exact Appendix-F address is in Gmail code/config tests. | PASS |
| 52 | One counted match per opponent | Forbidden beyond one | Ledger exists, but opponent ID is derived from the generated game ID and ledger failure is swallowed. | FAIL |
| 53 | Git SHA in Step-0 | Mandatory | Builder contains invalid subprocess call and live signed Step-0 exchange is absent. | FAIL |
| 54 | Token totals in final JSON | Mandatory | Dataclass fields exist, but live result/report is not the signed agreement and does not populate them. | FAIL |
| 55 | Self-grade code quality only | Mandatory | Release documentation acknowledges the scope and does not award league-result points. | PASS |

## Baseline totals

`PASS=24`, `FAIL=25`, `EXTERNAL_PENDING=6`.

These counts are not a grade calculation. They are an implementation backlog.
Final PASS rows will be updated with an exact production symbol, exact test name,
and hashed runtime evidence artifact.

