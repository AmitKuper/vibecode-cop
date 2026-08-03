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
