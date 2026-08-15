# Appendix-E requirements traceability — Code-100 v11

Evidence basis: cop `0b968a6ff667dda76ce6b3b0d501a7955dca6172`; thief
`01ada2368a8612f3c854babb44e35630e07e60d3`. Appendix E defines the
rules; Appendix F defines quantitative values. Repository claims alone are not
evidence. Final statuses are only `PASS`, `FAIL`, or `EXTERNAL_PENDING`.

> **Reading note (2026-08-15).** Re-derived at the SHAs above. The per-row SHA columns
> were dropped: every row repeated the same two hashes, which is the header's job. The
> four rows that had closed since the last snapshot (10, 31, 32, 45) are now PASS on
> counted-series evidence; rules 41, 43 and 44 remain genuinely external (final tag,
> Moodle upload, per-member submission).

| Rule | Classification | Result | Production code | Tests | Runtime evidence | Notes |
| ---: | --- | --- | --- | --- | --- | --- |
| 1. Separate police/thief processes | Mandatory | PASS | `scripts/ref3_match/series_split.py`; `scripts/ref3_role_worker.py` | `test_split_architecture.py` | CV-09 real TCP process series | Separate PID/config/log/secret roots. |
| 2. No shared memory/variables | Forbidden | PASS | `scripts/ref3_match/worker_proc.py` (JSON-line pipes only) | process isolation tests | CV-09 | Only MCP messages cross processes. |
| 3. One Orchestrator entry point | Mandatory | PASS | `scripts/live_match_ref3.py` facade -> `scripts/ref3_match/cli.py` | `test_codex_counted_composition_series.py` | CV-03/CV-09 | Counted construction fails closed. |
| 4. Proper game state machine | Mandatory | PASS | `ProtocolCoordinator` | coordinator/state-machine suites | CV-03/CV-08 | Coordinator authorizes phases. |
| 5. Reject illegal state transitions | Mandatory | PASS | `cop_worker/mcp/coordinator.py` | adversarial ordering tests | CV-08 | No permissive fallback. |
| 6. Deadline tracking/deadlock prevention | Mandatory | PASS | `cop_worker/reliability/deadline_tracker.py` | `test_codex_deadline_tracker.py` | CV-03/CV-08 | Counted timeout becomes technical loss. |
| 7. Independent Watchdog/recovery | Mandatory | PASS | `cop_worker/reliability/watchdog.py`; `scripts/ref3_match/watchdog_bridge.py` | `test_watchdog.py`; chaos tests | CV-08/CV-09 | Heartbeat failure fails closed. |
| 8. Live GUI shows local truth | Mandatory | PASS | `SafeLiveView` | GUI/leak suites | CV-03 | Real screenshot is external pending. |
| 9. Never show objective board | Forbidden | PASS | `LiveViewModel`; `LocalObservation` | hidden-coordinate leak tests | CV-03 | Opponent coordinate absent. |
| 10. Public tunnel exposure | Mandatory | PASS | `docs/DEPLOYMENT.md` static-IP topology | N/A external | counted series evidence | Five outside groups reached us across the internet; see `results/counted_series.json`. |
| 11. Byte-identical shared config | Mandatory | PASS | canonical config/hash | config mismatch suites | CV-06/CV-09 | Both bind `45ce5e…db90`. |
| 12. Minimums increase only by agreement | Mandatory | PASS | `config_validator.py` | Appendix-F conformance tests | CV-03 | Fixed/minimum/negotiated distinguished. |
| 13. Orthogonal or STAY movement | Mandatory | PASS | `apply_joint_action` | domain conformance | CV-03/CV-09 | One physical authority. |
| 14. No diagonal movement | Forbidden | PASS | legal mask + domain validation | illegal-action tests | CV-03 | Unknown actions rejected. |
| 15. Declare barrier placement openly | Mandatory | PASS | `PLACE_*` commit/reveal/audit | barrier/audit tests | CV-09 | Audited physical action. |
| 16. Never lie about barrier location | Forbidden | PASS | canonical derived target | barrier conformance | CV-03/CV-09 | No separate location claim. |
| 17. SHA-256 Commit-Reveal | Mandatory | PASS | gamelet-bound commitment helpers | `test_audit_adversarial_consensus.py`, `test_audit_adversarial_journal.py` | CV-08/CV-09 | Actual gamelet/step bound. |
| 18. Nonce secret until final audit | Mandatory | PASS | journal/audit serializers | nonce privacy tests | CV-09 public scan | Zero public nonce values. |
| 19. Audit mismatch is technical loss | Mandatory | PASS | audit exact-set validator | hostile tamper matrix | CV-08 | No audit downgrade. |
| 20. Trusted Replay reconstruction | Mandatory | PASS | `ReplayApp` canonical reconstruction | replay tamper/reconstruction tests | CV-08 | Trusted Step-0 keys, roots, six gamelets. |
| 21. Truthfully declare capture | Mandatory | PASS | `TransitionResult.outcome` | outcome authority tests | CV-03/CV-09 | No legacy terminal authority. |
| 22. Reject false capture | Forbidden | PASS | peer result validators | false-claim tests | CV-08 | Outcome/score recomputed. |
| 23. Lock scent model at Step-0 | Mandatory | PASS | dual scent in immutable domain state | scent/profile tests | CV-09 signed Step-0 | One canonical scent authority. |
| 24. Signed hardware declaration | Mandatory | PASS | signed Step-0 declaration | signing/declaration tests | CV-09, 12 signatures | Includes Git/model/dependencies. |
| 25. LLM out of movement; RL primary | Recommended + project mandatory | PASS | recurrent role policy | recurrent failure/strategy suites | CV-06/CV-07 | Missing model aborts counted. |
| 26. Free natural language | Mandatory | PASS | `NaturalLanguagePolicy` | language intent tests | CV-03 | Four contextual intents. |
| 27. No numeric-location verbal protocol | Forbidden | PASS | hint validation | language guard tests | CV-08 | Strategic text remains free. |
| 28. Gmail token bucket | Mandatory | PASS | Gatekeeper/token bucket | Gmail fake-service tests | CV-08/CV-09 | Production path invoked. |
| 29. Gmail DOS detector | Mandatory | PASS | DOS detector/circuit breaker | Gmail abuse tests | CV-08 | Counted failure closes. |
| 30. Send-only Gmail authorization | Mandatory | PASS | OAuth scope validator | scope tests | CV-08/CV-10 | Only `gmail.send`. |
| 31. Minimum outside groups | Mandatory | PASS | `results/counted_series.json` | N/A external | counted series evidence | Five distinct groups: anrbj666, imreeyal, uoh-sqak, rstabcde, najamjad. |
| 32. Automatic Gmail result report | Mandatory | PASS | `scripts/league_artifacts/report.py` via the Gmail Gatekeeper | fake Gmail tests PASS | counted series evidence | Five real sends; message IDs recorded per series in the ledger. |
| 33. Final report is signed JSON | Mandatory | PASS | signed `ResultAgreement` serializer | report schema tests | CV-09 | Includes gamelets/totals/signatures. |
| 34. No free-text final report | Forbidden | PASS | Gatekeeper JSON validation | rejection tests | CV-08 | Canonical JSON only. |
| 35. Identical bilateral result; both report | Mandatory | PASS | bilateral result consensus | bilateral/result tests | CV-09, two signatures/outboxes | Byte-identical agreement. |
| 36. Comprehensive mutual audit | Mandatory | PASS | bilateral audit summary/exact sets | audit adversarial suite | CV-08/CV-09, 12 audits | Roots/config/profile/score/tokens bound. |
| 37. Accurate prior-match declaration | Mandatory | PASS | league ledger + Step-0 | ledger tests | CV-09 | Stable opponent identity. |
| 38. False match count disqualifies | Forbidden | PASS | declaration validator | false-count tests | CV-08 | Rejected before commitment. |
| 39. Never commit secrets | Forbidden | PASS | secret hygiene | secret/privacy tests | CV-10 | Tracked scan clean. |
| 40. Credential files ignored | Mandatory | PASS | `.gitignore` | ignore/secret tests | CV-10 | OAuth/runtime secrets excluded. |
| 41. Documented final Git tag | Mandatory | EXTERNAL_PENDING | release workflow | tag checks | EXT-04 | Tag/push only after final gate. |
| 42. Accurate academic README | Mandatory | PASS | `README.md` | document validator | CV-11 | Current architecture/limits. |
| 43. Moodle PDF unchanged layout | Mandatory | EXTERNAL_PENDING | external checklist | N/A external | EXT-03 | Moodle access required. |
| 44. Every member submits separately | Mandatory | EXTERNAL_PENDING | external checklist | N/A external | EXT-03 | Human participation required. |
| 45. Real unique eight-character group ID | Mandatory | PASS | `config/runtime.toml` `[identity] group_id` | validator tests | counted series evidence | `vibecode` - eight characters, in every declaration and on the wire. |
| 46. Barrier-on-thief captures | Mandatory | PASS | canonical transition | exact domain vector | CV-03 | Appendix-F behavior. |
| 47. Trapped thief is caught | Mandatory | PASS | canonical transition/outcome | trapped-thief tests | CV-03 | Escape set computed canonically. |
| 48. Fixed scoring table | Mandatory | PASS | config + result recomputation | scoring tests | CV-03/CV-09 | 20/5, 5/10, 2/2. |
| 49. Two cross-linked repositories | Mandatory | PASS | companion README links | document validator | CV-11 | Both repos verified together. |
| 50. README/config/PRD/PLAN/TODO | Mandatory | PASS | required documents | document validator | CV-11 | Present in both repos. |
| 51. Correct lecturer report recipient | Mandatory | PASS | report config | recipient tests | CV-08 | Appendix-F value used. |
| 52. One counted match per opponent | Forbidden beyond one | PASS | league ledger admission | repeat-opponent tests | CV-08/CV-09 | Counted repeat fails closed. |
| 53. Git SHA in Step-0 | Mandatory | PASS | clean Git guard/declaration | provenance tests | CV-09 exact SHA | Signed by each role. |
| 54. Token totals in final JSON | Mandatory | PASS | token accounting/result agreement | token tests | CV-08/CV-09 | Per gamelet + series arithmetic. |
| 55. Self-grade code quality only | Mandatory | PASS | strict verifier dimensions | verifier/document tests | final machine report | External/league points excluded. |

Totals: **52 PASS, 0 FAIL, 3 EXTERNAL_PENDING**.

Every code-verifiable rule passes at the SHAs above. The three remaining rows are
external by nature and cannot close inside the repository: rule 41 (the FINAL git
tag - `v5.0-submission` is pushed in both repos but commits have landed since, so
re-tag at hand-in), rule 43 (Moodle PDF upload) and rule 44 (each member submitting
separately).
