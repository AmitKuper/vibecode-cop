# Mail-report format — guidance from the course lecturer's reference agent

**Source:** NotebookLM "Game-P2P-Cop-Chase Repository Chat" (the lecturer's reference repository,
`rmisegal/Game-P2P-Cop-Chase`), 2026-08-08. Screenshot on file with the vibecode operators.

This records the lecturer-side confirmation that our email-report design is the intended one:
**only the small `result` JSON goes in the mail; the bulky log/config artifacts are committed to
the repo, not emailed.**

## Question asked
"Should we add these files [the log/config artifacts] to the email too, or not?"

## Answer (the reference agent, paraphrased from the chat)
It is **not recommended (and not intended)** to attach the log files to the email, for several
reasons rooted in the project's architecture docs:

1. **Result JSON is the condensed report.** `result_<game_id>.json` is designed to condense all
   relevant information from the sub-game logs into the league table — it already carries
   `log_verified: true` and the mutual cryptographic signatures, so there is no need to send the
   full logs to prove the games settled.
2. **Log JSON files are large.** They contain every step, board state, SHA-256 hashes and
   `prompt_discussion` / LLM interactions — meant for a **Replay Player**, not for email.
3. **Architecture guideline.** `docs/UPGRADE-4JSON-TODO.md` step 6: *"wire EmailSender to send
   the result JSON"* — i.e., only the result JSON rides the mail body.
4. **Series load.** A full series = 6 sub-games → 14 files (1 declaration, 6 logs, 6 configs,
   1 result), but only the **result** is emailed; the rest live in the repo.

## How vibecode implements it (matches the guidance)
- `scripts/ref3_artifacts.py::email_result` sends **one** email per team: the `result` JSON as the
  body **and** the same bytes as the single attachment — nothing else.
- All four artifact kinds (config, log, declaration, result) are written to the repo; only the
  result is emailed.
- Counted runs email the result to `rmisegal+uoh26finalgame@gmail.com` (rule 51); the settlement
  guard emits the report only on a clean 6/6.

> Note: the raw NotebookLM screenshot (Image) is the primary source; if the PNG is saved to a path
> it can be dropped in alongside this file. This markdown transcribes its substance.
