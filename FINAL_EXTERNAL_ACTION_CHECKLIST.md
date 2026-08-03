# Final External Action Checklist

All items below require real-world actions that cannot be completed by code alone.
Complete these before the course deadline.

## Identity and Configuration

- [ ] **Obtain 8-character group ID** from course (currently only "placeholder" / "XXXXXXXX" in configs).
  Update `group_id` in `game_config.toml` and in the thief repo's config.
  The validator (`agent/step0/validator.py`) will reject counted mode until this is set.

## RL Model Training

- [ ] **Train RL model checkpoint** (requires GPU, approx. hours to days of training).
  Run `uv run python -m agent.rl.train_cli --mode selfplay --steps 1000000`.
  After training, update `models/MANIFEST.json` with real `sha256`, `training_steps`, and `evaluation_win_rate`.
  Update `PeerDeclaration.model_sha256` in your Step-0 declaration accordingly.
  Current state: `models/MANIFEST.json` records `training_steps: 0` and `evaluation_win_rate: 0.0`.

## Gmail OAuth Credentials

- [ ] **Set up Gmail OAuth credentials** with `gmail.send` scope only (see `docs/GMAIL_REPORTING_RUNBOOK.md`).
  Place `credentials.json` in the `secrets/` directory (git-ignored).
  Run `uv run python -m agent.gmail.auth` to generate `token.json`.
  Verify scope is limited to `gmail.send` — no read access.

## Real Opponent Matches

- [ ] **Run at least 2 real counted series** against different opponent groups.
  Each series must be a 6-gamelet counted match as defined in `agent/game_series.py`.
  Both cop and thief must run on separate machines connected via public tunnels.
  After each series, verify the LeagueLedger entry is written to `results/ledger.json`.

## Public Tunnel Evidence

- [ ] **Collect public tunnel evidence** (URLs, timestamps, connection logs).
  Use ngrok or cloudflared as documented in `docs/DEPLOYMENT_TUNNEL_RUNBOOK.md`.
  Save tunnel URLs and timestamps to `evidence/tunnel_evidence.txt`.

## Gmail Report Verification

- [ ] **Verify both Gmail reports sent and received** by rmisegal+uoh26finalgame@gmail.com.
  Both cop process and thief process must each send independently (Rule 35 — bilateral).
  Save Gmail message IDs to `evidence/gmail_message_ids.txt`.
  Check that the report body is valid JSON (schema: `ResultAgreement`).

## GUI and Replay Screenshots

- [ ] **Take live GUI screenshots** during an active game session.
  The live view must show only your own position (cop sees cop; thief sees thief).
  Save screenshots to `evidence/screenshots/live_view_cop.png` and `live_view_thief.png`.

- [ ] **Take Replay Viewer screenshots** after a completed game.
  The replay must show the hash-chain verification status as "valid".
  Save screenshot to `evidence/screenshots/replay_viewer.png`.

## Match Evidence

- [ ] **Populate `evidence/` directory** with real match logs and report message IDs.
  Include: gamelet journals, bilateral AuditSummary JSONs, ResultAgreement JSONs.
  Evidence directory should be committed (no secrets; logs only).

## Moodle Submission

- [ ] **Fill in Moodle PDF** without moving or resizing any fields (Rule 43 — unchanged layout).
  Use only the designated input fields in the original course PDF template.

- [ ] **Each team member submits individually** to Moodle (Rule 44).
  Do NOT submit once on behalf of the whole team.

## Group ID Verification

- [ ] **Verify correct group ID** is reflected in both repos' `game_config.toml` and in
  `PeerDeclaration.group_id` before the counted match series begins.
  The validator will raise an error if the group ID is fewer than 8 characters or is a placeholder.

---

**Traceability:** Items above correspond to EXTERNAL_PENDING rules:
1 (two-process), 10 (tunnel), 20 (replay screenshots), 25 (RL training, currently FAIL),
30 (Gmail credentials), 31 (opponent groups), 32 (Gmail send), 35 (bilateral send),
43 (Moodle PDF), 44 (individual submission), 45 (group ID), 55 (self-grade note).
