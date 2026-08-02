# Report Plugin Infrastructure — Implementation Plan

## 1. Goal

Create a plugin-based report infrastructure for the agent. Keep the existing local report generation, and add a Gmail API plugin that satisfies the final game-reporting requirement.

The game loop should only call one high-level operation:

```python
await report_manager.generate_all(context)
```

The report manager decides which plugins run.

## 2. Target Structure

Use or adapt the existing structure:

```text
agent/reports/
  __init__.py
  base.py                 # ReportPlugin, ReportContext, ReportResult
  manager.py              # ReportManager
  bundle.py               # ReportBundleBuilder / required file collector
  file_report.py          # JSON + Markdown local report plugin
  gmail_report.py         # Gmail API delivery plugin
  gatekeeper.py           # idempotency, rate limits, quota guard
  delivery_store.py       # report_delivery.json persistence
  plugin_factory.py       # config -> plugins
  errors.py
```

If the repository already has some of these files, extend them instead of replacing them blindly.

## 3. Phase 1 — Define report contracts

Create or update `agent/reports/base.py`:

```python
@dataclass(frozen=True)
class ReportContext:
    game_id: str
    role: str
    group_id: str
    game_dir: Path
    game_state: dict
    result: dict | None
    config_hash: str | None
    log_hash: str | None
    required_files: list[Path]
    metadata: dict[str, Any]


@dataclass
class ReportResult:
    plugin: str
    ok: bool
    status: str
    destination: str | None = None
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class ReportPlugin(Protocol):
    name: str

    async def generate(self, context: ReportContext) -> ReportResult: ...
```

Keep the plugin contract small. Do not pass many unrelated arguments into plugins.

## 4. Phase 2 — Build report context and bundle

Create `agent/reports/bundle.py`.

Responsibilities:

1. Locate or create the required report files:
   - `declaration_<game_id>.json`
   - `config_<game_id>_g<NN>.json`
   - `log_<game_id>_g<NN>.json`
   - `result_<game_id>.json`
2. Add existing internal files if present:
   - `report.json`
   - `report.md`
   - `moves.jsonl`
   - `game_state.json`
3. Return a `ReportContext` with paths to all files.

Do this after final audit / game end and before external delivery.

## 5. Phase 3 — Update ReportManager

Update `agent/reports/manager.py`:

```python
class ReportManager:
    def __init__(self, plugins: list[ReportPlugin]):
        self.plugins = plugins

    async def generate_all(self, context: ReportContext) -> dict[str, ReportResult]:
        results = {}
        for plugin in self.plugins:
            try:
                results[plugin.name] = await plugin.generate(context)
            except Exception as e:
                results[plugin.name] = ReportResult(
                    plugin=plugin.name,
                    ok=False,
                    status="failed",
                    error=str(e),
                )
        return results
```

Plugin failures must not stop other plugins.

## 6. Phase 4 — Keep local file plugins

Keep or refactor `FileReportPlugin` so it supports:

```toml
[reports.file_json]
enabled = true

[reports.file_markdown]
enabled = true
```

It should generate:

```text
agent/memory/<game_id>/report.json
agent/memory/<game_id>/report.md
```

Run file plugins before Gmail so Gmail can attach their outputs.

## 7. Phase 5 — Implement GmailReportPlugin

Create `agent/reports/gmail_report.py`.

Use Gmail API, not SMTP password login.

Core behavior:

1. Load config.
2. Respect mode: `disabled`, `dry_run`, `draft`, `send`.
3. Validate required files exist.
4. Ask gatekeeper if sending is allowed.
5. Build MIME email.
6. Attach required files.
7. Use Gmail API with OAuth 2.0 and send-only scope.
8. Store delivery result.

Required scope:

```python
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
```

Public plugin result examples:

```json
{
  "plugin": "gmail",
  "ok": true,
  "status": "sent",
  "destination": "configured-recipient",
  "details": {"message_id": "..."}
}
```

```json
{
  "plugin": "gmail",
  "ok": true,
  "status": "dry_run",
  "destination": "local-preview.eml"
}
```

## 8. Phase 6 — Gmail config

Add private config fields, for example in `cop/config.toml` and `thief/config.toml`:

```toml
[reports]
enabled = true
plugins = ["file_json", "file_markdown", "gmail"]

[reports.gmail]
enabled = true
mode = "dry_run" # disabled | dry_run | draft | send
recipient = "configured-recipient@example.com"
credentials_path = "secrets/gmail/credentials.json"
token_path = "secrets/gmail/token.json"
attach_required_files = true
attach_markdown_summary = true
max_attachments_mb = 20
max_sends_per_day = 10
```

Do not put the real recipient in public documentation. Use placeholders in committed examples.

## 9. Phase 7 — Secrets and .gitignore

Update `.gitignore`:

```gitignore
# Gmail OAuth secrets
credentials.json
token.json
secrets/
*.credentials.json
*.token.json
.env
```

Also make sure tests do not require real Gmail credentials.

## 10. Phase 8 — Gatekeeper

Create `agent/reports/gatekeeper.py`.

Required checks:

- report already sent for this `game_id` and plugin
- daily send limit
- minimum interval between sends
- max attachment size
- retry count
- repeated failure lockout

Default behavior:

- If already sent, return skipped.
- If in `dry_run`, do not require Gmail credentials.
- If in `send`, require OAuth token or clear setup error.

## 11. Phase 9 — Delivery store

Create `agent/reports/delivery_store.py`.

Persist delivery status to:

```text
agent/memory/<game_id>/report_delivery.json
```

Example:

```json
{
  "game_id": "game_001",
  "deliveries": [
    {
      "plugin": "gmail",
      "mode": "send",
      "status": "sent",
      "timestamp": "2026-07-20T12:00:00Z",
      "message_id": "..."
    }
  ]
}
```

## 12. Phase 10 — Integrate with game end

In orchestrator/game runtime, after game end and final audit:

```python
context = await ReportBundleBuilder(...).build(game_id, game_state)
plugins = ReportPluginFactory.from_config(config.reports)
report_results = await ReportManager(plugins).generate_all(context)
logger.info("Report results: %s", report_results)
```

Do not call Gmail directly from the game loop.

## 13. Phase 11 — Tests

Add tests:

```text
tests/test_reports_base.py
tests/test_report_manager.py
tests/test_report_bundle.py
tests/test_gmail_report_dry_run.py
tests/test_gmail_report_gatekeeper.py
tests/test_report_plugin_failure_isolated.py
```

Required test cases:

- file plugins generate JSON/Markdown
- Gmail dry_run creates message preview without credentials
- Gmail send refuses missing credentials
- duplicate send is skipped
- attachment missing is reported clearly
- one plugin failure does not stop other plugins
- `.gitignore` contains Gmail token/credential patterns

## 14. Migration from current EmailReportPlugin

Current email plugin design may be SMTP-oriented. Keep it only as optional legacy if needed, but the required mail-report implementation should be `GmailReportPlugin` using Gmail API OAuth 2.0.

Recommended migration:

1. Leave `EmailReportPlugin` disabled or mark legacy.
2. Add `GmailReportPlugin`.
3. Register Gmail plugin through config.
4. Make dry_run the default.
5. Enable `send` only for the final verified run.

## 15. Done Definition

This task is done when:

- Report plugins are loaded from config.
- Local file reports still work.
- Gmail plugin supports `dry_run` and `send`.
- Gmail plugin uses OAuth and `gmail.send` only.
- Gmail secrets are ignored by Git.
- Required game files are included in the report bundle.
- A failed Gmail send does not break saved game state.
- Tests pass.
