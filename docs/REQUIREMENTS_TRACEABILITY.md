# Appendix-E Requirements Traceability — Final Code-Readiness

Evidence date: 2026-08-05. Appendix E supplies the rules and Appendix F supplies
the quantitative values. Status is restricted to `PASS`, `FAIL`, and
`EXTERNAL_PENDING`. A PASS below requires production wiring plus executable
evidence; the strict verifier re-runs that evidence with no accepted skips.

| # | Binding rule | Class | Production and executable evidence | Status |
|---:|---|---|---|---|
| 1 | Police and thief are separate processes | Mandatory | Role CLIs plus `scripts/verify_local_two_process.py` launch two independent Python processes over TCP for the counted series. | PASS |
| 2 | No shared memory/variables | Forbidden | The acceptance processes use separate configurations, secrets, ports, logs, game directories, and process memory; only MCP messages cross the boundary. | PASS |
| 3 | Orchestrator is the single subsystem entry | Mandatory | `agent/role_cli.py::_resolved` creates counted `AgentOrchestrator`; `test_codex_counted_composition.py` proves active/passive fail-closed composition. | PASS |
| 4 | Proper game state machine | Mandatory | `ProtocolCoordinator` authorizes the counted transitions; state-machine and production lifecycle suites run in CV-03. | PASS |
| 5 | Reject illegal state transitions | Mandatory | Coordinator guards and adversarial ordering tests reject out-of-sequence phases. | PASS |
| 6 | Deadline tracking prevents deadlock | Mandatory | Counted Orchestrator owns `DeadlineTracker`; timeout and production lifecycle tests plus bounded real-process verification pass. | PASS |
| 7 | Independent Watchdog/recovery | Mandatory | Counted CLI starts the independent Watchdog and fails on startup/recovery errors; `test_watchdog.py` and chaos paths run in CV-08. | PASS |
| 8 | Live GUI shows local truth only | Mandatory | Counted publication goes through `SafeLiveView`; `test_live_view_model.py`, UI route tests, and composition tests cover the production call. | PASS |
| 9 | Never show objective board | Forbidden | Local-view serializers reject opponent coordinates; leak/adversarial GUI and observation tests run in the full suite. | PASS |
| 10 | Public tunnel exposure | Mandatory | Requires a genuine public endpoint and outside connectivity; no tunnel evidence is fabricated locally. | EXTERNAL_PENDING |
| 11 | Byte-identical shared config | Mandatory | Both champions and signed Step-0 bind config SHA `45ce5e…db90`; mismatch tests and CV-09 verify bilateral equality. | PASS |
| 12 | Minimums only increase by agreement | Mandatory | `canonical_config.py` applies Appendix-F fixed/minimum semantics and signed negotiation locks the result; conformance tests pass. | PASS |
| 13 | Orthogonal or stand movement only | Mandatory | Every physical action reaches `agent/domain/transition.py::apply_joint_action`; domain and real lifecycle evidence pass. | PASS |
| 14 | No diagonal movement | Forbidden | Legal-action masking plus canonical domain validation reject diagonal/unknown movement in active and passive paths. | PASS |
| 15 | Declare every barrier placement openly | Mandatory | `PLACE_*` is committed, revealed, audited, and applied by the canonical transition; barrier conformance tests pass. | PASS |
| 16 | Never lie about barrier location | Forbidden | Barrier target is derived solely from the disclosed action and actor coordinate; no independent location claim exists. | PASS |
| 17 | SHA-256 Commit-Reveal | Mandatory | Both peers use `create_commitment`; CV-09 verifies six bilateral commit/reveal journals and signatures. | PASS |
| 18 | Nonce secret until final audit | Mandatory | Gameplay reveal omits nonce; final audit alone discloses it. Nonce-isolation and public-artifact scans pass. | PASS |
| 19 | Audit mismatch causes technical loss | Mandatory | Audit/peer-result validation turns mismatches into technical loss/abort; `test_audit_adversarial.py` and bilateral tests run in CV-08. | PASS |
| 20 | Replay reconstruction and verification | Mandatory | Counted audit bundle and signed result are durable trust anchors; replay/tamper suites reconstruct and reject modifications. | PASS |
| 21 | Truthfully declare capture | Mandatory | Capture is derived by the canonical domain from geometry, not a peer assertion; active/passive consensus tests pass. | PASS |
| 22 | Reject false capture | Forbidden | Peer game-end and result validators reject outcome/score claims inconsistent with canonical state. | PASS |
| 23 | Lock scent model before game | Mandatory | Signed bilateral Step-0 carries and verifies the scent-model hash before the first commitment. | PASS |
| 24 | Signed hardware declaration before game | Mandatory | Signed bilateral Step-0 includes hardware/dependency declarations and verifies both public keys in CV-09. | PASS |
| 25 | Keep LLM from movement; project uses RL primary | Recommended + project mandatory | Counted order is local observation/belief/history → role recurrent champion → legal mask → canonical validation; model failure aborts. | PASS |
| 26 | Free natural language | Mandatory | Movement and language policies are separate; active/passive turn paths exchange truth/lie-capable natural-language hints. | PASS |
| 27 | No numeric-location verbal protocol | Forbidden | Language guards reject numeric coordinate protocols while permitting free strategic text; language suites pass. | PASS |
| 28 | Gmail token bucket | Mandatory | Counted report uses Gatekeeper with token bucket; fake-service and production-pipeline tests pass. | PASS |
| 29 | Gmail DOS detector | Mandatory | Gatekeeper owns DOS detector/circuit breaker; retry/abuse tests pass. | PASS |
| 30 | Send-only Gmail authorization | Mandatory | OAuth setup/runtime requests only `gmail.send`; scope-contract tests and tracked scan pass. | PASS |
| 31 | Minimum outside groups | Mandatory | At least two real different course groups must participate; local fixtures cannot prove this. | EXTERNAL_PENDING |
| 32 | Automatic result report via Gmail API | Mandatory | Code path, independent role reports, validation, and fake transport pass; genuine provider delivery/message IDs require credentials. | EXTERNAL_PENDING |
| 33 | Final report is valid signed JSON | Mandatory | Counted terminal path serializes the signed `ResultAgreement`, per-gamelet data, totals, hashes, and signatures; strict peer parsing passes. | PASS |
| 34 | No free-text final report | Forbidden | Gatekeeper rejects non-JSON report bodies; counted sender passes only canonical JSON. | PASS |
| 35 | Identical bilateral result; each peer reports | Mandatory | CV-09 checks byte-identical agreement bodies, two role signatures, consensus, and two independent fake outbox records. | PASS |
| 36 | Comprehensive mutual audit | Mandatory | Both peers audit all six journals, bind audit keys from Step-0, exchange signed summaries, and reject incomplete/tampered bundles. | PASS |
| 37 | Accurate prior counted-match declaration | Mandatory | Signed Step-0 derives prior-match count from the role-local league ledger and peer validation compares the declaration. | PASS |
| 38 | False match count disqualifies | Forbidden | Signed-declaration and ledger-consistency tests reject false prior-count claims before commitments. | PASS |
| 39 | Never commit secrets | Forbidden | CV-10 scans all tracked text for private-key/provider-token signatures; counted artifacts expose no nonces or secrets. | PASS |
| 40 | Credential files in `.gitignore` | Mandatory | Both repositories ignore OAuth credentials, tokens, local secrets, and runtime evidence directories. | PASS |
| 41 | Documented final Git tag | Mandatory | A final audited tag must be created and pushed only after the final clean verification. | EXTERNAL_PENDING |
| 42 | Comprehensive accurate academic README | Mandatory | Both READMEs document current counted CLI, recurrent champions, strict verifier, and honest external boundary. | PASS |
| 43 | Moodle PDF unchanged layout | Mandatory | Requires the official course form and human submission; local code cannot establish it. | EXTERNAL_PENDING |
| 44 | Each member submits separately | Mandatory | Requires individual human Moodle actions and cannot be automated or fabricated. | EXTERNAL_PENDING |
| 45 | Real unique eight-character group ID | Mandatory | Validation exists, but the actual course identity must be supplied by the team. | EXTERNAL_PENDING |
| 46 | Barrier placed on thief captures | Mandatory | Canonical simultaneous transition places the declared legal barrier and captures when it lands on the thief; conformance tests pass. | PASS |
| 47 | Trapped thief is caught | Mandatory | Canonical domain detects no legal escape and applies the Appendix-F caught outcome; exact trapped tests pass. | PASS |
| 48 | Fixed scoring table | Mandatory | Canonical configuration fixes 20/5, 5/10, and 2/2 tie scoring; agreement recomputation rejects deviations. | PASS |
| 49 | Two repositories with cross-links | Mandatory | Both role repositories exist and each README links its companion. | PASS |
| 50 | README/config/PRD/PLAN/TODO in each repo | Mandatory | CV-11 validates all required academic/release artifacts in both repositories. | PASS |
| 51 | Lecturer agent report address | Mandatory | Counted Gmail configuration and tests use the exact Appendix-F recipient. | PASS |
| 52 | One counted match per opponent | Forbidden beyond one | League ledger uses the stable opponent identity, Step-0 declares history, and counted mode fails closed on repeats/ledger errors. | PASS |
| 53 | Git SHA in Step-0 | Mandatory | Counted clean-worktree guard obtains exact HEAD; all 12 signed Step-0 declarations in CV-09 carry their role's exact SHA. | PASS |
| 54 | Token totals in final JSON | Mandatory | Per-gamelet and series prompt/completion/total fields are explicit, arithmetically checked, signed, and peer-validated. | PASS |
| 55 | Self-grade code quality only | Mandatory | Numeric verifier score covers code-verifiable gates only; league results and external evidence are excluded from the self-grade. | PASS |

## Final status totals

`PASS=48`, `FAIL=0`, `EXTERNAL_PENDING=7`.

This is a code-readiness trace, not proof of completed external course actions.
Real Gmail, public/outside matches, the final pushed tag, actual group identity,
and Moodle evidence remain pending until genuine artifacts exist.

