# Report Plugin Infrastructure — Requirements

## 1. Purpose

The agent must contain a plugin-based report infrastructure that can support multiple independent report implementations. One required implementation is a Gmail API report plugin that sends the required post-game report after a legal game ends.

This document defines what the report system must do, not how it must be implemented internally.

## 2. Scope

The report infrastructure must support:

- Local report generation to files.
- External report delivery through plugins.
- A Gmail API plugin for final game reporting.
- Safe development modes such as `disabled`, `dry_run`, or `draft`.
- Extensibility for future report outputs without changing the game loop.

The report infrastructure is not part of the MCP game protocol. It runs only after the game reaches a valid terminal state or technical terminal state.

## 3. Existing Context

The current agent design already describes a report plugin architecture with:

- `ReportPlugin` base class.
- `FileReportPlugin` for JSON/Markdown reports.
- `EmailReportPlugin` placeholder.
- `ReportManager` that runs all registered plugins.

The new requirement is to formalize this as a general report plugin infrastructure and replace/extend the email implementation with a Gmail API based plugin that satisfies the project mail-report requirement.

## 4. Functional Requirements

### R1 — Report manager

The system must provide a `ReportManager` responsible for:

- Registering report plugins.
- Running all enabled plugins after game completion.
- Passing each plugin the same immutable report context.
- Collecting each plugin result.
- Logging plugin success/failure.
- Preventing one failed plugin from stopping the others.

### R2 — Report plugin interface

Every report plugin must implement a common interface similar to:

```python
class ReportPlugin:
    name: str

    async def generate(self, context: ReportContext) -> ReportResult:
        ...
```

The interface must be async-compatible because some plugins perform I/O, such as Gmail API calls.

### R3 — Report context

The report system must build one canonical `ReportContext` after the game ends.

The context must include at least:

- `game_id`
- agent `role`
- group identity
- opponent identity if known
- start/end timestamps
- final winner/result
- final score
- final board state
- move count
- path to game directory
- path to generated report files
- path to required attachment files
- config hash
- log hash if available
- audit/verification status

### R4 — Required output files

Before external delivery, the report infrastructure must ensure the required game files exist:

- `declaration_<game_id>.json`
- `config_<game_id>_g<NN>.json`
- `log_<game_id>_g<NN>.json`
- `result_<game_id>.json`

If the existing implementation also creates internal files such as `report.json`, `report.md`, `moves.jsonl`, or `game_state.json`, those can remain, but they do not replace the required files above.

### R5 — Local file report plugin

The system must keep a local file report plugin that can generate:

- JSON summary report.
- Markdown summary report.

This plugin should run before the Gmail plugin so the Gmail plugin can attach or reference the generated reports.

### R6 — Gmail report plugin

The system must provide a Gmail API report plugin, for example:

```text
GmailReportPlugin
```

It must:

- Send the final game report to the configured recipient.
- Use Gmail API with OAuth 2.0.
- Use the send-only Gmail scope.
- Attach the required JSON files where possible.
- Include a concise human-readable email body.
- Include enough identifiers in the subject/body to associate the report with the game.
- Run only after the game reaches a reportable terminal state.

### R7 — Gmail plugin must not use SMTP password login

The Gmail implementation must not require or store a Gmail account password.

Allowed:

- OAuth 2.0 `credentials.json` for local authorization setup.
- OAuth 2.0 `token.json` generated after first authorization.
- Gmail API `gmail.send` scope.

Disallowed:

- Gmail password in TOML.
- App password in TOML.
- SMTP login as the required reporting path.
- Full mailbox scopes such as read/modify/full Gmail access.

### R8 — Gmail scope

The Gmail plugin must use least privilege:

```python
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
```

The plugin must not request mailbox read, modify, delete, or full-access scopes.

### R9 — Secrets and Git safety

The following files must never be committed:

- `credentials.json`
- `token.json`
- any OAuth token cache
- any `.env` file containing secrets

The repository must include `.gitignore` rules for these files.

The Gmail plugin config must allow paths to these files, but the files themselves must stay local/private.

### R10 — Config-driven behavior

The reporting system must be configured from private agent config, not from the shared game config.

Example:

```toml
[reports]
enabled = true
plugins = ["file_json", "file_markdown", "gmail"]

[reports.gmail]
enabled = true
mode = "draft" # disabled | dry_run | draft | send
recipient = "configured-recipient@example.com"
credentials_path = "secrets/gmail/credentials.json"
token_path = "secrets/gmail/token.json"
attach_required_files = true
attach_markdown_summary = true
max_attachments_mb = 20
```

The recipient must be configurable. Do not hardcode personal or lecturer email addresses in code or public docs.

### R11 — Safe modes

The Gmail plugin must support at least:

- `disabled`: do nothing and return skipped status.
- `dry_run`: build message and attachments but do not call Gmail.
- `draft`: create a Gmail draft if implemented, or save an `.eml`/preview locally if draft is not supported.
- `send`: send the actual email.

During development, default mode should be `dry_run` or `draft`, not `send`.

### R12 — Gatekeeper protections

Before sending, the Gmail plugin must pass through a report gatekeeper that prevents accidental spam or quota problems.

The gatekeeper must provide:

- Per-game idempotency: do not send the same game report multiple times unless explicitly forced.
- Rate limit.
- Daily send limit.
- Attachment size limit.
- Retry limit with backoff.
- Fail-fast behavior for suspicious loops or repeated failures.

### R13 — Idempotency

The system must record delivery status in a durable local file, for example:

```text
agent/memory/<game_id>/report_delivery.json
```

It must include:

- plugin name
- mode
- recipient hash or recipient string depending on privacy choice
- timestamp
- status
- Gmail message id or draft id if available
- error if failed

A second run must detect an already successful send and skip by default.

### R14 — Email subject

The Gmail report subject must be deterministic and searchable.

Example:

```text
Cop-Thief Game Report | <game_id> | group=<group_id> | role=<role> | result=<winner>
```

### R15 — Email body

The email body must include at least:

- Game id.
- Group id/name.
- Role: cop/thief.
- Opponent group if known.
- Result/winner.
- Score if available.
- Start/end timestamps.
- Config hash.
- Log hash or audit status.
- List of attached files.
- Repository/tag/commit if available.

### R16 — Attachments

The Gmail plugin must attach the required report files when they exist and are within size limits.

Required preferred attachments:

- `declaration_<game_id>.json`
- `config_<game_id>_g<NN>.json`
- `log_<game_id>_g<NN>.json`
- `result_<game_id>.json`

Optional attachments:

- `report.md`
- `report.json`
- compressed archive of logs if needed

If attachments are too large, the plugin must fail safely or attach a compact summary and clearly report what was omitted.

### R17 — Error handling

A report plugin failure must not corrupt game state.

Errors must be represented as structured results:

```json
{
  "ok": false,
  "plugin": "gmail",
  "error_code": "gmail_auth_missing",
  "message": "Gmail OAuth token is missing. Run authorization setup first."
}
```

### R18 — Observability

The report infrastructure must log:

- plugin start/end
- selected mode
- files generated
- attachments selected
- skipped sends
- successful delivery
- failed delivery and reason

Logs must not print OAuth tokens or secret contents.

## 5. Non-Functional Requirements

### Security

- Use Gmail API OAuth 2.0, not passwords.
- Use send-only scope.
- Keep credentials out of Git.
- Avoid leaking recipient/token data in logs.

### Reliability

- Local report files must still be created even if Gmail delivery fails.
- Gmail delivery must be retryable without duplicate sending.
- Plugin failures must be isolated.

### Extensibility

- Adding a future plugin must not require changing the game loop.
- Plugins should be registered from configuration or a plugin factory.

### Testability

The Gmail plugin must support dependency injection or a mock Gmail service for tests.

## 6. Acceptance Criteria

The implementation is complete when:

- `ReportManager` can run multiple plugins.
- Local JSON/Markdown reports are generated.
- Required game files are collected into a report bundle.
- `GmailReportPlugin` can build a valid Gmail API message with attachments.
- `GmailReportPlugin` uses OAuth 2.0 and `gmail.send` only.
- `credentials.json` and `token.json` are ignored by Git.
- `dry_run` mode works without Gmail credentials.
- `send` mode sends exactly one report per game by default.
- Duplicate send attempts are skipped unless forced.
- Unit tests cover success, missing credentials, duplicate send, attachment missing, and plugin failure isolation.
