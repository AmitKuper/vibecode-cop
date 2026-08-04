# Final External Action Checklist — v7

All items below require real-world actions that cannot be completed by code alone.
Complete these before the course deadline.

**Legend:**
- `[CODE_FAIL]` — corresponding rule is FAIL in the RTM; code wiring needed before the external action is even relevant
- `[EXTERNAL]` — code is ready; only an external action (credentials, match, course action) is needed

---

## Priority 1: Wire Bilateral Audit and Gmail Send in Code (Rules 35, 36)

These are CODE FAILS that require a developer action first, then the external action:

- [ ] **[CODE_FAIL] Rule 36 — Wire AuditSummary into do_final_audit** (`agent/peer_runtime_audit.py`)
  After `run_final_audit()` returns, construct `AuditSummary` from the result dict.
  Exchange it with the opponent via a new MCP `final_summary` phase message.
  Call `verify_bilateral_consensus()` with both `SignedResultAgreement` objects.
  Expected: `do_final_audit` returns `AuditSummary` instead of `(bool, dict)`.

- [ ] **[CODE_FAIL] Rule 35 — Call Gatekeeper.send() at game end** (`agent/peer_runtime.py`)
  After the audit completes, construct `ResultAgreement` from `AuditSummary`.
  Call `from agent.gmail.gatekeeper import Gatekeeper; Gatekeeper().send(RECIPIENT, subject, body)`.
  Both cop and thief processes must call this independently (bilateral send requirement).
  Expected: each process sends one email per counted series.

---

## Priority 2: Identity and Configuration (Rule 45)

- [ ] **[EXTERNAL] Obtain 8-character group ID** from course (currently "placeholder" / "XXXXXXXX" in configs).
  Update `group_id` in `config/game_config.toml` for BOTH repos (thief and cop).
  The validator (`agent/step0/validator.py`) rejects counted mode until this is set to exactly 8 non-placeholder chars.

---

## Priority 3: RL Model Training (Rule 25)

- [ ] **[EXTERNAL] Train RL model checkpoint** (requires GPU; expect hours to days).
  ```
  uv run python -m agent.rl.train_cli --mode selfplay --steps 1000000
  ```
  After training, update `models/MANIFEST.json`:
  - `sha256` — real SHA-256 of the `.pt` file
  - `training_steps` — must be > 0
  - `evaluation_win_rate` — must be > 0.0 (competitive threshold: ≥0.55)
  
  Current state: `models/MANIFEST.json` records `training_steps: 0` and `evaluation_win_rate: 0.0`.
  The `.pt` files are placeholder-initialized weights only.

---

## Priority 4: Gmail OAuth Credentials (Rule 30, prerequisite for Rule 32)

- [ ] **[EXTERNAL] Set up Gmail OAuth credentials** with `gmail.send` scope only.
  See `docs/GMAIL_REPORTING_RUNBOOK.md` for step-by-step instructions.
  Place `credentials.json` in the `secrets/` directory (already git-ignored).
  Run `uv run python -m agent.gmail.auth` to generate `token.json`.
  **Verify scope is limited to `gmail.send` only — no read access.**

---

## Priority 5: Real Opponent Matches (Rules 31, 32, and prerequisite for 35 external)

- [ ] **[EXTERNAL] Run at least 2 real counted series** against different opponent groups.
  Each series must be a 6-gamelet counted match as defined in `agent/game_series.py`.
  Both cop and thief processes must run on separate machines via public tunnels.
  After each series, verify `LeagueLedger` entry in `results/ledger.json`:
  ```
  python -c "import json; print(json.load(open('results/ledger.json')))"
  ```

---

## Priority 6: Public Tunnel Evidence (Rule 10)

- [ ] **[EXTERNAL] Collect public tunnel evidence** (URLs, timestamps, connection logs).
  Use ngrok or cloudflared as documented in `docs/DEPLOYMENT_TUNNEL_RUNBOOK.md`:
  ```
  ngrok tcp 8080   # for thief
  ngrok tcp 8081   # for cop (separate terminal)
  ```
  Save tunnel URLs and timestamps to `evidence/tunnel_evidence.txt`.
  Commit `evidence/` directory (no secrets; logs only).

---

## Priority 7: Gmail Report Verification (Rules 32, 35)

- [ ] **[EXTERNAL] Verify both Gmail reports sent and received** by `rmisegal+uoh26finalgame@gmail.com`.
  Both cop process and thief process must send independently (Rule 35 bilateral requirement).
  Save Gmail message IDs to `evidence/gmail_message_ids.txt`.
  Verify report body is valid JSON matching `ResultAgreement` schema:
  ```python
  import json

  body = open("evidence/last_report_body.json").read()
  data = json.loads(body)  # must not raise
  assert "token_totals" in data
  ```

---

## Priority 8: GUI and Replay Screenshots (Rule 20)

- [ ] **[EXTERNAL] Take live GUI screenshots** during an active game session.
  The live view must show only your own position (cop sees cop; thief sees thief).
  Save screenshots to:
  - `evidence/screenshots/live_view_cop.png`
  - `evidence/screenshots/live_view_thief.png`

- [ ] **[EXTERNAL] Take Replay Viewer screenshots** after a completed game.
  The replay must show the hash-chain verification status as "VALID".
  Save screenshot to `evidence/screenshots/replay_viewer.png`.

---

## Priority 9: Moodle Submission (Rules 43, 44)

- [ ] **[EXTERNAL] Fill in Moodle PDF** without moving or resizing any fields (Rule 43 — unchanged layout).
  Use only the designated input fields in the original course PDF template.

- [ ] **[EXTERNAL] Each team member submits individually** to Moodle (Rule 44).
  Do NOT submit once on behalf of the whole team.

---

## Summary Table

| Rule | Status | Action |
|------|--------|--------|
| 10 | EXTERNAL_PENDING | Public tunnel evidence |
| 20 | EXTERNAL_PENDING | Replay viewer screenshots |
| 25 | FAIL | GPU train RL model (training_steps=0 now) |
| 30 | EXTERNAL_PENDING | Gmail OAuth credentials (gmail.send scope only) |
| 31 | EXTERNAL_PENDING | Run counted series against ≥2 different groups |
| 32 | EXTERNAL_PENDING | Real Gmail send (needs credentials + opponents) |
| 35 | FAIL | Wire Gatekeeper.send() into peer_runtime.py (code fix) |
| 36 | FAIL | Wire AuditSummary into do_final_audit() (code fix) |
| 43 | EXTERNAL_PENDING | Moodle PDF (unchanged layout) |
| 44 | EXTERNAL_PENDING | Individual Moodle submission per member |
| 45 | EXTERNAL_PENDING | 8-char group ID from course |
| 55 | EXTERNAL_PENDING | Self-grade acknowledgement |

---

**Traceability:**
- FAIL rules (25, 35, 36) require developer code fixes before external evidence is possible
- EXTERNAL_PENDING rules (10, 20, 30, 31, 32, 43, 44, 45, 55) require only external actions once code is complete
- After fixing rules 35 and 36, the score estimate rises from ~78 to ~85 before any external actions
