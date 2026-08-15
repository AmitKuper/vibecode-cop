# Appendix-E requirements traceability — Code-100 v11

Evidence basis: cop `dedaaf147989d1b63f4d4536330bf70335df4630`; thief
`55d45fcd4010884b08c64380fe03c6cd39062266`. Appendix E defines the
rules; Appendix F defines quantitative values. Repository claims alone are not
evidence. Final statuses are only `PASS`, `FAIL`, or `EXTERNAL_PENDING`.

> **Reading note (2026-08-15).** This matrix is a snapshot taken at the SHAs above.
> The *Production code* column has since been repointed at the files that exist
> today (the `agent/` package it originally cited was deleted), but the verdicts and
> runtime-evidence IDs were not re-derived at the current SHA. Four rows have
> demonstrably closed since the snapshot and are no longer `EXTERNAL_PENDING`:
> rule 10 (public exposure — met via a router-forwarded static public IP,
> `docs/KNOWN_DEVIATIONS.md` D1), rule 31 (five distinct outside groups played),
> rule 32 (real Gmail sends, message IDs in `results/counted_series.json`), and
> rule 45 (group ID `vibecode`, eight characters, in every declaration). Rules 41,
> 43 and 44 remain genuinely external. Treat the totals line at the bottom as
> historical.

| Rule | Classification | Result | Production code | Tests | Runtime evidence | Cop SHA | Thief SHA | Notes |
|---:|---|---|---|---|---|---|---|---|
| 1. Separate police/thief processes | Mandatory | PASS | `scripts/ref3_match/series_split.py`; `scripts/ref3_role_worker.py` | `test_split_architecture.py` | CV-09 real TCP process series | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Separate PID/config/log/secret roots. |
| 2. No shared memory/variables | Forbidden | PASS | `scripts/ref3_match/worker_proc.py` (JSON-line pipes only) | process isolation tests | CV-09 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Only MCP messages cross processes. |
| 3. One Orchestrator entry point | Mandatory | PASS | `scripts/live_match_ref3.py` facade -> `scripts/ref3_match/cli.py` | `test_codex_counted_composition_series.py` | CV-03/CV-09 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Counted construction fails closed. |
| 4. Proper game state machine | Mandatory | PASS | `ProtocolCoordinator` | coordinator/state-machine suites | CV-03/CV-08 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Coordinator authorizes phases. |
| 5. Reject illegal state transitions | Mandatory | PASS | `cop_worker/mcp/coordinator.py` | adversarial ordering tests | CV-08 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | No permissive fallback. |
| 6. Deadline tracking/deadlock prevention | Mandatory | PASS | `cop_worker/reliability/deadline_tracker.py` | `test_codex_deadline_tracker.py` | CV-03/CV-08 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Counted timeout becomes technical loss. |
| 7. Independent Watchdog/recovery | Mandatory | PASS | `cop_worker/reliability/watchdog.py`; `scripts/ref3_match/watchdog_bridge.py` | `test_watchdog.py`; chaos tests | CV-08/CV-09 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Heartbeat failure fails closed. |
| 8. Live GUI shows local truth | Mandatory | PASS | `SafeLiveView` | GUI/leak suites | CV-03 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Real screenshot is external pending. |
| 9. Never show objective board | Forbidden | PASS | `LiveViewModel`; `LocalObservation` | hidden-coordinate leak tests | CV-03 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Opponent coordinate absent. |
| 10. Public tunnel exposure | Mandatory | EXTERNAL_PENDING | tunnel runbook | N/A external | EXT-01 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Requires public infrastructure. |
| 11. Byte-identical shared config | Mandatory | PASS | canonical config/hash | config mismatch suites | CV-06/CV-09 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Both bind `45ce5e…db90`. |
| 12. Minimums increase only by agreement | Mandatory | PASS | `config_validator.py` | Appendix-F conformance tests | CV-03 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Fixed/minimum/negotiated distinguished. |
| 13. Orthogonal or STAY movement | Mandatory | PASS | `apply_joint_action` | domain conformance | CV-03/CV-09 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | One physical authority. |
| 14. No diagonal movement | Forbidden | PASS | legal mask + domain validation | illegal-action tests | CV-03 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Unknown actions rejected. |
| 15. Declare barrier placement openly | Mandatory | PASS | `PLACE_*` commit/reveal/audit | barrier/audit tests | CV-09 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Audited physical action. |
| 16. Never lie about barrier location | Forbidden | PASS | canonical derived target | barrier conformance | CV-03/CV-09 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | No separate location claim. |
| 17. SHA-256 Commit-Reveal | Mandatory | PASS | gamelet-bound commitment helpers | `test_audit_adversarial_consensus.py`, `test_audit_adversarial_journal.py` | CV-08/CV-09 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Actual gamelet/step bound. |
| 18. Nonce secret until final audit | Mandatory | PASS | journal/audit serializers | nonce privacy tests | CV-09 public scan | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Zero public nonce values. |
| 19. Audit mismatch is technical loss | Mandatory | PASS | audit exact-set validator | hostile tamper matrix | CV-08 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | No audit downgrade. |
| 20. Trusted Replay reconstruction | Mandatory | PASS | `ReplayApp` canonical reconstruction | replay tamper/reconstruction tests | CV-08 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Trusted Step-0 keys, roots, six gamelets. |
| 21. Truthfully declare capture | Mandatory | PASS | `TransitionResult.outcome` | outcome authority tests | CV-03/CV-09 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | No legacy terminal authority. |
| 22. Reject false capture | Forbidden | PASS | peer result validators | false-claim tests | CV-08 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Outcome/score recomputed. |
| 23. Lock scent model at Step-0 | Mandatory | PASS | dual scent in immutable domain state | scent/profile tests | CV-09 signed Step-0 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | One canonical scent authority. |
| 24. Signed hardware declaration | Mandatory | PASS | signed Step-0 declaration | signing/declaration tests | CV-09, 12 signatures | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Includes Git/model/dependencies. |
| 25. LLM out of movement; RL primary | Recommended + project mandatory | PASS | recurrent role policy | recurrent failure/strategy suites | CV-06/CV-07 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Missing model aborts counted. |
| 26. Free natural language | Mandatory | PASS | `NaturalLanguagePolicy` | language intent tests | CV-03 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Four contextual intents. |
| 27. No numeric-location verbal protocol | Forbidden | PASS | hint validation | language guard tests | CV-08 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Strategic text remains free. |
| 28. Gmail token bucket | Mandatory | PASS | Gatekeeper/token bucket | Gmail fake-service tests | CV-08/CV-09 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Production path invoked. |
| 29. Gmail DOS detector | Mandatory | PASS | DOS detector/circuit breaker | Gmail abuse tests | CV-08 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Counted failure closes. |
| 30. Send-only Gmail authorization | Mandatory | PASS | OAuth scope validator | scope tests | CV-08/CV-10 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Only `gmail.send`. |
| 31. Minimum outside groups | Mandatory | EXTERNAL_PENDING | league runbook | N/A external | EXT-01 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Needs two real groups. |
| 32. Automatic Gmail result report | Mandatory | EXTERNAL_PENDING | independent Gatekeeper pipelines | fake Gmail tests PASS | EXT-02 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Real IDs require OAuth. |
| 33. Final report is signed JSON | Mandatory | PASS | signed `ResultAgreement` serializer | report schema tests | CV-09 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Includes gamelets/totals/signatures. |
| 34. No free-text final report | Forbidden | PASS | Gatekeeper JSON validation | rejection tests | CV-08 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Canonical JSON only. |
| 35. Identical bilateral result; both report | Mandatory | PASS | bilateral result consensus | bilateral/result tests | CV-09, two signatures/outboxes | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Byte-identical agreement. |
| 36. Comprehensive mutual audit | Mandatory | PASS | bilateral audit summary/exact sets | audit adversarial suite | CV-08/CV-09, 12 audits | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Roots/config/profile/score/tokens bound. |
| 37. Accurate prior-match declaration | Mandatory | PASS | league ledger + Step-0 | ledger tests | CV-09 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Stable opponent identity. |
| 38. False match count disqualifies | Forbidden | PASS | declaration validator | false-count tests | CV-08 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Rejected before commitment. |
| 39. Never commit secrets | Forbidden | PASS | secret hygiene | secret/privacy tests | CV-10 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Tracked scan clean. |
| 40. Credential files ignored | Mandatory | PASS | `.gitignore` | ignore/secret tests | CV-10 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | OAuth/runtime secrets excluded. |
| 41. Documented final Git tag | Mandatory | EXTERNAL_PENDING | release workflow | tag checks | EXT-04 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Tag/push only after final gate. |
| 42. Accurate academic README | Mandatory | PASS | `README.md` | document validator | CV-11 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Current architecture/limits. |
| 43. Moodle PDF unchanged layout | Mandatory | EXTERNAL_PENDING | external checklist | N/A external | EXT-03 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Moodle access required. |
| 44. Every member submits separately | Mandatory | EXTERNAL_PENDING | external checklist | N/A external | EXT-03 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Human participation required. |
| 45. Real unique eight-character group ID | Mandatory | EXTERNAL_PENDING | group-ID validators | validator tests | EXT-03 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Real identity not guessed. |
| 46. Barrier-on-thief captures | Mandatory | PASS | canonical transition | exact domain vector | CV-03 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Appendix-F behavior. |
| 47. Trapped thief is caught | Mandatory | PASS | canonical transition/outcome | trapped-thief tests | CV-03 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Escape set computed canonically. |
| 48. Fixed scoring table | Mandatory | PASS | config + result recomputation | scoring tests | CV-03/CV-09 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | 20/5, 5/10, 2/2. |
| 49. Two cross-linked repositories | Mandatory | PASS | companion README links | document validator | CV-11 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Both repos verified together. |
| 50. README/config/PRD/PLAN/TODO | Mandatory | PASS | required documents | document validator | CV-11 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Present in both repos. |
| 51. Correct lecturer report recipient | Mandatory | PASS | report config | recipient tests | CV-08 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Appendix-F value used. |
| 52. One counted match per opponent | Forbidden beyond one | PASS | league ledger admission | repeat-opponent tests | CV-08/CV-09 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Counted repeat fails closed. |
| 53. Git SHA in Step-0 | Mandatory | PASS | clean Git guard/declaration | provenance tests | CV-09 exact SHA | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Signed by each role. |
| 54. Token totals in final JSON | Mandatory | PASS | token accounting/result agreement | token tests | CV-08/CV-09 | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | Per gamelet + series arithmetic. |
| 55. Self-grade code quality only | Mandatory | PASS | strict verifier dimensions | verifier/document tests | final machine report | `dedaaf147989d1b63f4d4536330bf70335df4630` | `55d45fcd4010884b08c64380fe03c6cd39062266` | External/league points excluded. |

Totals: **48 PASS, 0 FAIL, 7 EXTERNAL_PENDING**.

The code-verifiable result may reach 100 only after the exact-current-SHA verifier
passes. Full submission readiness remains false until the seven external rows are
closed with genuine evidence.
