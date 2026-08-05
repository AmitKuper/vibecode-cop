# Final 100-Readiness Report

Evidence date: 2026-08-05
Release state: **CODE_VERIFIABLE PASS — EXTERNAL ACTIONS PENDING**

## Outcome

The strict executable verifier passed every local gate on clean source revisions:

- Cop verified source: `b9f672381fb3c456a0a6fdb3f99a113750333548`
- Thief verified source: `aedbcb854a2e20579a1540732693d4c721955814`
- Code-verifiable gates: **11 PASS, 0 FAIL, 0 skipped**
- Code-verifiable score: **100/100**
- Appendix-E trace: **48 PASS, 0 FAIL, 7 EXTERNAL_PENDING**
- Full submission ready: **no**; genuine external evidence is outstanding.

The numeric 100 is intentionally limited to code-verifiable quality. It excludes
league performance points and does not claim that public-network, real-Gmail,
identity, tag-push, or Moodle obligations are complete.

## Clean quality evidence

| Gate | Cop | Thief |
|---|---:|---:|
| `uv sync --frozen` / `uv lock --check` | PASS / PASS | PASS / PASS |
| Full pytest | 1,467 passed, 0 skipped | 1,340 passed, 0 skipped |
| Actual branch coverage | 1,615/1,882 = 85.8130% | 1,603/1,882 = 85.1753% |
| Ruff lint / format | PASS / PASS | PASS / PASS |
| CLI subprocess startup | PASS | PASS |
| Hostile adaptive/audit/replay/Watchdog/Gmail/token suite | 130 passed | 130 passed |
| Tracked secret scan | PASS | PASS |

No mandatory subsystem is hidden by a broad coverage omission. The verifier has
no skip option and fails if any full or focused suite reports a skip.

## Counted production evidence

The verifier launched exactly two independent Python role processes over real
localhost TCP and completed exactly six counted gamelets:

- Series: `series_20260805_064801_ea4d7c38`
- Signed Step-0 declarations verified: 12
- Signed passing audits verified: 12
- Result signatures verified: 2
- Bilateral agreement hash:
  `d731f5be9ee9b33d20f01787772df864bd77102bf0d08561ff29784e89233ce3`
- Shared ledger-consensus hash:
  `99b5f6d55f54266af3a9c9abd0df6d3b4a36b20a2ac75a5c57fdce6ba55a7c93`
- Public nonce-value keys: 0
- Per-gamelet and series token totals: explicit, signed, arithmetically checked
- Independent fake acceptance reports: 2, both explicitly marked fake

The role-local ledgers correctly have different `opponent_id` values while their
match ID, declaration/result hashes, signatures, timestamp, and chain fields
match. A first verifier attempt incorrectly demanded byte-identical independent
ledgers; it failed closed. The corrected reciprocal-identity/shared-facts check
was committed and the entire clean verifier was rerun successfully.

## Champion and tournament evidence

| Role | Champion SHA-256 | Held-out paired series / gamelets | Win rate | Worst family | Technical failures |
|---|---|---:|---:|---:|---:|
| Cop | `1c6f85bed3ba754d1daa38aa394b455d605fe1768436532581cc118b5be96949` | 600 / 3,600 | 89.00% | 79.03% | 0 |
| Thief | `477c56ad7348dfc6dd9130e3ed371be8afbc912ef34635ee0fb56ef2427d6151` | 150 / 900 | 76.11% | 34.44% | 0 |

Both are checksum-verified `RecurrentA2C-GRU` policies bound to canonical
configuration `45ce5eeb0daff048c31c1d5012b3db55b4b101f91146d4a886474e024ea8db90`.
Each passed its paired official-score promotion gate against the strongest
held-out baseline with diverse opponent families and zero technical failures.

## Final code path

`CLI → RuntimeMode.COUNTED → AgentOrchestrator → signed bilateral Step-0 →
adaptive negotiation and locked ProtocolProfile → six gamelets → canonical
domain transition → LocalObservation/BeliefState/recurrent champion → legal mask
→ Commit-Reveal → bilateral audit → signed identical ResultAgreement → independent
league ledgers → independent Gatekeeper report → DONE`

Missing models, dirty Git state, incompatible protocols, illegal actions, audit
or result disagreement, ledger failure, and report failure all abort counted mode.

## External boundary

The following remain **EXTERNAL_PENDING**:

- real public tunnel and matches with at least two distinct outside groups;
- real Gmail OAuth delivery from both roles and two provider message IDs;
- the actual unique eight-character course group ID;
- the official unmodified-layout PDF, screenshots, and individual Moodle submissions;
- creation and push of the final audited tags/commits.

Localhost and fake-Gmail artifacts are code acceptance evidence only and never
stand in for these real-world actions.
