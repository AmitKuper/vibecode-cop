# Release Checklist — v2.0-submission

## Code Quality Gates

- [x] Tests pass: 1095 passing, 0 failures
- [x] Coverage: >=85% branch (enforced in CI)
- [x] Ruff lint: 0 violations
- [x] Ruff format: clean

## Protocol Correctness

- [x] 16-state protocol state machine
- [x] Commit-reveal with Ed25519 signatures
- [x] Bilateral hash-chain audit
- [x] ResultAgreement bilateral signing
- [x] Watchdog independent OS-process freeze detection
- [x] Deadline tracker on all external calls
- [x] Gatekeeper rate-limiting on Gmail

## Documentation

- [x] README.md — accurate, no stale claims
- [x] docs/SCENT_AND_BELIEF_SPEC.md
- [x] docs/RL_REPRODUCTION.md
- [x] docs/DEPLOYMENT_TUNNEL_RUNBOOK.md
- [x] docs/KNOWN_DEVIATIONS.md
- [x] docs/RELEASE_CHECKLIST.md (this file)
- [x] docs/PROMPT_ENGINEERING_LOG.md
- [x] docs/PROGRAM_EXECUTION_LEDGER.md
- [x] .github/workflows/ci.yml

## Infrastructure

- [x] CI pipeline: .github/workflows/ci.yml
- [x] Version: pyproject.toml v2.0.0, agent/version.py
- [x] results/verification_manifest.json

## External Evidence Required (PENDING)

- [ ] Real opponent match: EXTERNAL_PENDING
- [ ] Trained RL checkpoint: EXTERNAL_PENDING
- [ ] Gmail OAuth credentials: EXTERNAL_PENDING
- [ ] Public tunnel evidence: EXTERNAL_PENDING
- [ ] Group ID (8-char): EXTERNAL_PENDING
- [ ] GUI screenshots in browser: EXTERNAL_PENDING
- [ ] Moodle submission: EXTERNAL_PENDING
