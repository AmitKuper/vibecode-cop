# Known Deviations from Original Specification

## Active Deviations

### D1: Public Tunnel Match — EXTERNAL_PENDING

Real opponent match across the internet requires separate machines and a public
tunnel (ngrok/Cloudflare). Not demonstrated in this submission.
See docs/DEPLOYMENT_TUNNEL_RUNBOOK.md for the runbook.

### D2: Trained RL Checkpoint — EXTERNAL_PENDING

The PPO training infrastructure (`agent/rl/`) is complete. A trained checkpoint
requires a GPU training run (~12 hours on A100) not performed in this submission.
See docs/RL_REPRODUCTION.md for reproduction instructions.

### D3: Real Gmail Send — EXTERNAL_PENDING

Gmail reporting infrastructure is implemented (`agent/reports/gmail_reporter.py`).
Sending real emails requires OAuth 2.0 credentials (client_secret.json) not
included in this repository. See docs/GMAIL_REPORTING_RUNBOOK.md.

### D4: Group ID — EXTERNAL_PENDING

The 8-character group ID is assigned by the course instructor and has not been
received yet.

### D5: GUI Screenshots — EXTERNAL_PENDING

The live GUI (`agent/gui/app.py`) and replay viewer (`agent/replay/app.py`)
are fully implemented. Browser screenshots require a running browser environment
not available in the CI headless runner.

### D6: config_validator.py Retained

`agent/config_validator.py` is retained for backward compatibility. Eight legacy
tests in `tests/test_shared_config_contract.py` depend on it. The module has
been superseded by `agent/mcp/config_hash.py` for production use.

## Resolved Deviations (corrected in prior phases)

- DEV-002: Empty Audit Vacuously Valid — CORRECTED in Phase 0
- DEV-003: Trapped Thief Never Triggering COP_WIN — CORRECTED in Phase 0
- DEV-005: FastAPI Tests Skipped — CORRECTED in Phase 0

## Professionalization pass — 2026-08-10 (intentional deviations, with evidence)

1. **Email report format.** The result email sends the canonical result JSON as body +
   the same bytes as a single named attachment (not the book Appendix-A prose listing).
   APPROVED by the lecturer's reference agent — evidence:
   `evidence/Email_Report_Agent_conversation.jpeg`. The remaining artifact kinds are
   published in the repos and reached via the result's `links.github` (rule 49).
2. **Hardcoded own-inbox default recipient** (`agentsorch@gmail.com` in the Gmail
   gatekeeper + match runner). Deliberate safety rail: the league/lecturer address is
   NEVER stored in code or config (test-enforced by
   `tests/test_config_single_source.py::test_runtime_toml_has_no_league_address`) and
   enters only by hand via `--report-to` on counted day. An address the run cannot
   reach cannot be mailed by accident.
3. **Static-IP topology** (no tunnel): production runs on a router port-forwarded
   static IP (cop 61224 / thief 61223). The tunnel runbook is retained for the
   alternative topology only.
4. **150-line file limit — largely met; remainder tracked.** Every module over 390
   lines was split into <=150-line packages/mixins (reference-v3 wire, kit fixtures,
   the trainer, coordinator, gamelet, replay, the adaptive-protocol stack) with
   suites green and a full 6/6 kit-sparring rehearsal after the change. Remaining
   over-limit files (~26, all 150-260 lines, plus scripts/live_match_ref3.py) are
   cohesive single-responsibility units; the production match runner is deliberately
   kept whole while live league windows are possible (a mid-refactor wire layer is a
   rule-35 risk). One deliberate exception class: domain/transition.py holds the
   single wire-law transition function, byte-pinned by kit vectors — splitting it
   adds risk without cohesion benefit.
5. **Two-repo module duplication** (cop_worker ↔ league_manager protocol copies and
   the cop/thief sibling repos): the course mandates two independent repositories;
   within this repo every duplicated league_manager module is now an import alias of
   the cop_worker canonical (single source of truth, cannot drift).
