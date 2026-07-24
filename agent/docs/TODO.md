# Report Plugin Infrastructure — TODO

**Status:** Planned  
**Owner:** Implementation  
**Priority:** High  
**Deadline:** Phase by phase  

---

## Phase 1: Define Report Contracts ⏳

- [ ] Create `agent/reports/base.py`
  - [ ] `ReportContext` dataclass (game_id, role, group_id, game_dir, game_state, result, config_hash, log_hash, required_files, metadata)
  - [ ] `ReportResult` dataclass (plugin, ok, status, destination, error, details)
  - [ ] `ReportPlugin` protocol (name, async generate method)
- [ ] Update `agent/reports/__init__.py` to export base classes

**Definition of Done:** All dataclasses and protocols defined, properly typed, frozen where appropriate.

---

## Phase 2: Build Report Bundle ⏳

- [ ] Create `agent/reports/bundle.py`
  - [ ] `ReportBundleBuilder` class
  - [ ] Locate/create required files:
    - [ ] `declaration_{game_id}.json`
    - [ ] `config_{game_id}_g<NN>.json`
    - [ ] `log_{game_id}_g<NN>.json`
    - [ ] `result_{game_id}.json`
  - [ ] Collect optional internal files (report.json, report.md, moves.jsonl, game_state.json)
  - [ ] Build `ReportContext` with all file paths
- [ ] Add methods:
  - [ ] `async build(game_id, game_state) -> ReportContext`
  - [ ] `_ensure_required_files()` — create empty stubs if missing
  - [ ] `_collect_optional_files() -> dict[str, Path]`

**Definition of Done:** Bundle builder creates proper context, all required files exist after build.

---

## Phase 3: Update ReportManager ⏳

- [ ] Create or update `agent/reports/manager.py`
  - [ ] `ReportManager` class (plugins list)
  - [ ] `async generate_all(context: ReportContext) -> dict[str, ReportResult]`
  - [ ] Error isolation: one plugin failure doesn't stop others
  - [ ] Logging: plugin start/end, success/failure
- [ ] Plugin execution order (file plugins first, then external)

**Definition of Done:** Manager can run multiple plugins, isolates failures, logs all events.

---

## Phase 4: Local File Plugins ⏳

- [ ] Create or update `agent/reports/file_report.py`
  - [ ] `FileReportPlugin` class
  - [ ] Supports `format="json"` or `format="markdown"`
  - [ ] Generate `report.json` (game summary)
  - [ ] Generate `report.md` (human-readable)
  - [ ] Config: `[reports.file_json]` and `[reports.file_markdown]`
- [ ] Integrate with ReportManager

**Definition of Done:** File reports generate to agent/memory/{game_id}/, accessible to Gmail plugin.

---

## Phase 5: Gmail Report Plugin ⏳

- [ ] Create `agent/reports/gmail_report.py`
  - [ ] `GmailReportPlugin` class
  - [ ] Config: mode (disabled|dry_run|draft|send), recipient, credentials_path, token_path
  - [ ] Mode support:
    - [ ] `disabled` — skip silently
    - [ ] `dry_run` — build message, don't send, save `.eml` preview
    - [ ] `draft` — create Gmail draft (if API supports)
    - [ ] `send` — send actual email via Gmail API
  - [ ] OAuth 2.0 integration:
    - [ ] Load `credentials.json`
    - [ ] Generate/load `token.json`
    - [ ] Scope: `https://www.googleapis.com/auth/gmail.send` only
  - [ ] Build MIME message:
    - [ ] Subject: `Cop-Thief Game Report | {game_id} | group={group_id} | role={role} | result={winner}`
    - [ ] Body: game_id, group_id, role, opponent, result, score, timestamps, config_hash, log_hash, file list
  - [ ] Attachment logic:
    - [ ] Required: declaration, config, log, result files
    - [ ] Optional: report.md, report.json
    - [ ] Respect `max_attachments_mb` (default 20)
  - [ ] Error handling: structured ReportResult with error codes
- [ ] Logging: mode, files, attachments selected, delivery status (no token leaking)

**Definition of Done:** Gmail plugin works in dry_run without credentials, send with proper OAuth, fails gracefully.

---

## Phase 6: Gmail Config ⏳

- [ ] Update `cop/config.toml`
  ```toml
  [reports]
  enabled = true
  plugins = ["file_json", "file_markdown", "gmail"]
  
  [reports.gmail]
  enabled = true
  mode = "dry_run"  # disabled | dry_run | draft | send
  recipient = "example@example.com"  # placeholder in public repo
  credentials_path = "secrets/gmail/credentials.json"
  token_path = "secrets/gmail/token.json"
  attach_required_files = true
  attach_markdown_summary = true
  max_attachments_mb = 20
  max_sends_per_day = 10
  ```
- [ ] Update `thief/config.toml` (same structure)
- [ ] Do NOT hardcode real email addresses in code or docs

**Definition of Done:** Config is readable, no secrets in public repo, templates are usable.

---

## Phase 7: Secrets and .gitignore ⏳

- [ ] Update `.gitignore` in project root:
  ```
  credentials.json
  token.json
  secrets/
  *.credentials.json
  *.token.json
  .env
  ```
- [ ] Update `.gitignore` in `cop/` and `thief/` if they have their own
- [ ] Add `secrets/gmail/.gitkeep` (directory marker, not secrets)
- [ ] Create `.env.example` template (no actual tokens)

**Definition of Done:** Secrets are never committed, templates guide users.

---

## Phase 8: Gatekeeper ⏳

- [ ] Create `agent/reports/gatekeeper.py`
  - [ ] `ReportGatekeeper` class
  - [ ] Check idempotency: report already sent for this game_id?
  - [ ] Check rate limits:
    - [ ] Daily send limit (default 10)
    - [ ] Minimum interval between sends (default 1 min)
  - [ ] Check attachment size (max_attachments_mb)
  - [ ] Check retry count (max 3)
  - [ ] Fail-fast on repeated failures
  - [ ] Load/check `agent/memory/{game_id}/report_delivery.json`
- [ ] Methods:
  - [ ] `async can_send(game_id, plugin, mode) -> (bool, reason_if_blocked)`
  - [ ] `async record_attempt(game_id, plugin, mode, status, message_id=None, error=None)`

**Definition of Done:** Duplicate sends blocked, rate limits enforced, logging clear.

---

## Phase 9: Delivery Store ⏳

- [ ] Create `agent/reports/delivery_store.py`
  - [ ] `DeliveryStore` class
  - [ ] Persist to `agent/memory/{game_id}/report_delivery.json`
  - [ ] Schema:
    ```json
    {
      "game_id": "...",
      "deliveries": [
        {
          "plugin": "gmail",
          "mode": "send",
          "status": "sent",
          "timestamp": "2026-07-20T12:00:00Z",
          "message_id": "...",
          "error": null
        }
      ]
    }
    ```
  - [ ] Methods:
    - [ ] `async has_successful_delivery(game_id, plugin) -> bool`
    - [ ] `async record(game_id, plugin, mode, status, message_id, error)`
    - [ ] `async get_delivery_history(game_id) -> list`

**Definition of Done:** Delivery history persists, idempotency check works.

---

## Phase 10: Integrate with Game End ⏳

- [ ] Update `agent/orchestrator.py` (game_end handler)
  - [ ] After game completion and final audit:
    ```python
    context = await ReportBundleBuilder(...).build(game_id, game_state)
    plugins = await ReportPluginFactory.from_config(config.reports)
    results = await ReportManager(plugins).generate_all(context)
    logger.info("Report results: %s", results)
    ```
  - [ ] Do NOT call Gmail directly from game loop
  - [ ] Catch and log report generation errors (don't break game state)
- [ ] Create `agent/reports/plugin_factory.py`
  - [ ] `ReportPluginFactory` class
  - [ ] `async from_config(reports_config) -> list[ReportPlugin]`
  - [ ] Register plugins based on enabled list

**Definition of Done:** Game end triggers reports, orchestrator doesn't hardcode plugin logic.

---

## Phase 11: Tests ⏳

Create tests in `agent/tests/`:

- [ ] `test_reports_base.py`
  - [ ] ReportContext frozen dataclass
  - [ ] ReportResult can be serialized
  - [ ] Plugin protocol enforced

- [ ] `test_report_manager.py`
  - [ ] Multiple plugins run
  - [ ] One plugin failure doesn't stop others
  - [ ] All results collected

- [ ] `test_report_bundle.py`
  - [ ] Required files created if missing
  - [ ] Optional files included if present
  - [ ] ReportContext has all expected fields

- [ ] `test_file_report_plugin.py`
  - [ ] JSON report generates
  - [ ] Markdown report generates
  - [ ] Files saved to correct location

- [ ] `test_gmail_report_dry_run.py`
  - [ ] dry_run mode works WITHOUT credentials
  - [ ] .eml preview generated locally
  - [ ] No Gmail API call made

- [ ] `test_gmail_report_send.py`
  - [ ] send mode REQUIRES credentials
  - [ ] OAuth token loaded correctly
  - [ ] Credentials missing → error (not exception)

- [ ] `test_gmail_report_gatekeeper.py`
  - [ ] Duplicate send blocked
  - [ ] Daily limit enforced
  - [ ] Retry count tracked

- [ ] `test_report_plugin_failure_isolated.py`
  - [ ] File plugin fails → Gmail still runs
  - [ ] Gmail fails → game state untouched
  - [ ] Results show which plugins failed

- [ ] `test_gitignore_gmail_secrets.py`
  - [ ] credentials.json ignored
  - [ ] token.json ignored
  - [ ] secrets/ ignored

**Definition of Done:** All tests pass, coverage ≥85%, no secrets in test fixtures.

---

## Phase 12: Documentation ⏳

- [ ] Update README: how to use report plugins
- [ ] Create `agent/docs/GMAIL_SETUP.md` (user guide for OAuth setup)
- [ ] Add examples to `agent/docs/REPORTS.md`

**Definition of Done:** User can follow setup guide to enable Gmail reporting.

---

## Migration from Current EmailReportPlugin ⏳

- [ ] Check if `EmailReportPlugin` exists in `agent/reports/`
  - [ ] If SMTP-based: mark as legacy, do NOT use for required mail-report
  - [ ] Keep optional for backward compatibility
  - [ ] Use `GmailReportPlugin` as the required implementation
- [ ] Default `mode="dry_run"` for safety during development
- [ ] Enable `send` only after testing passes

**Definition of Done:** Old SMTP plugin disabled, Gmail plugin is the new mail-report path.

---

## Acceptance Criteria ✅

- [x] Plan document reviewed
- [ ] Phase 1: Report contracts defined
- [ ] Phase 2: Bundle builder works
- [ ] Phase 3: ReportManager isolates failures
- [ ] Phase 4: File plugins generate JSON/Markdown
- [ ] Phase 5: Gmail plugin supports dry_run and send
- [ ] Phase 6: Config is flexible, no hardcoded emails
- [ ] Phase 7: Secrets ignored by Git
- [ ] Phase 8: Gatekeeper prevents duplicate sends
- [ ] Phase 9: Delivery history persists
- [ ] Phase 10: Game loop integrates reports
- [ ] Phase 11: Tests pass (≥85% coverage)
- [ ] Phase 12: Documentation complete
- [ ] Migration: Old plugin disabled, Gmail is default
- [ ] Final: All requirements met, no game state corruption on report failure

---

## Summary

**Total Phases:** 12 + migration  
**Estimated Implementation:** 8-12 hours  
**Testing:** 2-3 hours  
**Risk:** Medium (Gmail API integration, OAuth tokens)  
**Benefit:** Complete post-game reporting, extensible plugin system, no hardcoded emails  

Start with Phase 1 (contracts) and proceed sequentially.
