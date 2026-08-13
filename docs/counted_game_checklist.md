# Counted-game checklist — vibecode

Operational runbook for playing a **counted** league series. Tailored to vibecode's tooling:
a **single orchestrator** (`scripts/live_match_ref3.py --match`) serves both our MCP endpoints,
dials the opponent per window, runs six sub-games with the trained RL policy over the
reference-v3 wire, writes the four artifact kinds, and emails the result. This file is the
execution order; the same content lives in both repos (vibecode-cop, vibecode-thief).

A counted series is **one-shot and irreversible** (rule 52: one counted match per rival). Get the
before-steps green, then let it run — the settlement guard prevents a broken series from filing.

## Contacts / addresses

| Who | Address | Role |
|---|---|---|
| League / lecturer | `<LEAGUE_REPORT_ADDRESS>` | THE report address (rule 51) — counted only |
| vibecode operators | `agentsorch@gmail.com` (Ron Marom, Amit Kuperminz) | our Gmail sender + coordination |

## Our endpoints (static public IP, router-forwarded — no tunnel)

- cop: `http://62.56.220.143:61224/mcp` · thief: `http://62.56.220.143:61223/mcp`
- The `--match` process serves BOTH and dials the opponent's active one per window.

## Roles

The reference convention is alphabetical: the lower group_id is **cop on odd** sub-games
(g01/g03/g05), the other is **cop on even** (g02/g04/g06); thief moves first every sub-game.

**Our driver hardcodes** (`live_match_ref3.py`): vibecode = **thief on odd, cop on even**. This is
correct only when the opponent's group_id sorts BEFORE `vibecode` (as `anrbj666` does →
anrbj666 cop odd, vibecode cop even — and as `imreeyal` does: imreeyal police odd, confirmed in
their series-shape sentence in writing AND by two live friendlies 2026-08-10). ⚠️ Against an
opponent whose group_id sorts AFTER `vibecode`, the hardcoded split is inverted and MUST be fixed
(derive our role from the sorted pair) before that counted game.

## BEFORE (T-minus, in order)

1. **Written counted authorization (rule 52).** Both operators agree IN WRITING, before T, that
   this series is counted and is the single counted meeting. Exchange the declaration + our
   confirmation quoting it back with the exact `T = <date>, <time> Israel time`. Keep the
   messages — they are the authorization artifact. Nothing counts without it.
2. **Gmail token freshness.** `secrets/gmail/token.json` must be valid (a dead token = no report).
   It was used successfully the same day if we ran friendlies; otherwise re-mint before T.
3. **Shared constitution present.** `config/game.json` in BOTH repos, byte-identical (rule 11);
   `config_sha256 = 3b5c4a9a05c923acfe50ff355f56d4f529279435d87093aba6bad94015684f27` (imreeyal pairing).
4. **Both repos pushed, clean (rule 53).** Every sealed step-0 and result row carries our repo
   HEAD; the lecturer rev-parses it, so play a PUSHED commit. `git -C vibecode-cop rev-parse HEAD`
   and the same for vibecode-thief must be on origin.
5. **Know our counted count.** `--counted-played N` = our prior counted games, read from
   `results/counted_series.json` (`counted_games_played`). It is the count BEFORE this game (rules
   37-38); the lecturer cross-checks. (Currently 3 → next counted game passes `--counted-played 3`.)
6. **Endpoints up + cross-probe both directions (T−20).** Our two servers reachable from outside;
   the opponent's two URLs reachable from us (real MCP `list_tools`). Pass/fail in writing.
7. **PROTOCOL-LEVEL probe of the opponent (at pairing time AND at T−10) — not just TCP/406:**
   `uv run python scripts/preflight_opponent.py <their_url> [<their_url_2>]` runs tools/list
   introspection + our real reference-v3 discovery and prints ACCEPT or the exact refusal.
   A surface mismatch found here costs minutes; found at T it costs the window (najamjad,
   2026-08-13: superset tool schema refused by discovery — 30 seconds of this probe would
   have caught it hours early). Run it the FIRST time a new opponent's endpoint is ever live.
   Opponent endpoints returning `502`/`530` before they arm is NORMAL — the driver tolerates it
   and waits, but confirm they are actually serving by T.

## LAUNCH (at T)

Single command. With a saved opponent profile (`config/opponents/<group>/runtime.toml` — the
imreeyal profile carries URLs, group, chebyshev lock, and move engine), only THREE flags differ
from a friendly:

```bash
python scripts/live_match_ref3.py --match --config imreeyal   --report-to "<LEAGUE_REPORT_ADDRESS>"   --counted --counted-played 1
```

(The explicit `--opp-*-url/--opponent-group/--members` flags still work and override the
profile.) The league address is `rmisegal+uoh26finalgame@gmail.com` per the book's listing —
NEVER stored in config (test-enforced); verify the plus-tag against the latest course
announcement on the day.

- **Report goes to the league address ONLY** (single recipient; multi-recipient send is untested).
- If timing the launch, use a **file-based launcher** (`bash tmp/run_counted.sh`) that sleeps then
  runs. Do NOT use an inline `bash -c '...'` with `(...)` or `$(...)` in echoes — it breaks the
  nested quoting and the launch silently fails to parse (happened once; cost a window).

## DURING

- Touch nothing. Windows run strictly sequentially; each settles by mutual audit before the next.
- Terminal shows per-window `handshake OK`, `audit ok=True`, `outcome`, and (survival) `cop stops
  (no post-terminal move)`.
- The **settlement guard** files a report ONLY on a clean 6/6 (`audit: Verified OK` all six). A
  partial/failed series prints `REPORT WITHHELD` — no email, no ledger — and keeps artifacts
  locally for a per-window re-run. Nothing broken ever reaches the league.

## AFTER (the graded part)

1. **Verify the series settled:** log shows `STATUS: audits 6/6 ok`; the result reads 6/6
   `audit.log_verified`, `mutual_agreement.confirmed: true` with a hash equal to the opponent's.
2. **Verify the report email left:** `emailed result ONLY to <LEAGUE_REPORT_ADDRESS>
   (id=<msg-id>)`. Record the message-id. Rule 35: both teams' reports must exist and agree — get
   the opponent's message-id too.
3. **Commit + push ALL artifacts, both repos** — configs (`config/games/`) + logs + declaration +
   result + `counted_series.json` (`results/`). **These dirs are gitignored**, so use
   `git add -f`. Uncommitted artifacts are invisible to the audit; rule-53 hashes must resolve.
4. **Verify the counted tracker:** `results/counted_series.json` gained this series with the
   report message-id; `counted_games_played` incremented.
5. **Collect evidence** under `evidence/game_vs_<opponent>/` in EACH repo, split by the role that
   repo played: cop repo = its cop gamelets (config+log), thief repo = its thief gamelets; both
   get result + declaration + `counted_series.json` + the filed report `.eml` + a `README.md`.
   Add the runtime log and the authorization exchange. Tag both repos `game_vs_<opponent>`.
6. **Bump for next time:** the next counted game uses `--counted-played` = the new
   `counted_games_played`. No persistent config to edit — it is a CLI arg sourced from the ledger.
7. **Artifact swap + byte-diff** with the opponent (the friendly-#5 standard): sealed commits
   recompute, step-0s byte-identical to the wire, `config_sha256` equal, `mutual_agreement` equal,
   move commit-chain matches both directions. File the diff summary.

## Locked values (must appear in artifacts) — PER PAIRING

**imreeyal pairing (current; agreed in writing 2026-08-10, two friendlies played on it):**

| Field | Value |
|---|---|
| `config_sha256` (whole `game.json`) | `3b5c4a9a05c923acfe50ff355f56d4f529279435d87093aba6bad94015684f27` (reproduced byte-exact by BOTH teams) |
| `scent_model_sha256` (`subtractive_chebyshev_v1`) | `81ebee59640e80eae8ca9ee5f86abd26e7edf5cdbb27d15925cb6ee45ca6ddf4` |
| `wire_shape_sha256` (reference-v3) | `229ae6487a418c3fcb6da9be404de2f2533c288ebc228811bff6dedc4164d6f7` |
| `game_uid` (vs imreeyal) | `2e167349-f579-0201-e3f1-5ea0d75710c0` (both sides recomputed + declared at negotiate) |
| cell convention | every cell-valued wire field is **[row, col]** (settled in writing) |
| `tie_rule` | `series_add` (declared both sides) |
| diversity reward | winner-only flag on a counted first meeting: `diversity_reward_applied[winner]=true`; `total_score` unchanged (the +10 is a league standings bonus applied from the flag) |

**anrbj666 pairing (historical, counted game already played 2026-08-08):** config_sha256
`9ed3b2e9…`, scent `multiplicative_book_v1` `934c220d…`, uid `b2a16946-2cad-909f-60aa-b0cc8a8b7c4f`.

## Known pitfalls (from our runs, 2026-08-08)

- **Scheduler quoting:** never inline `bash -c` with `(...)`/`$()` in echoes — use a `.sh` file.
- **Artifacts gitignored:** `results/` (line 41) and `config/games` — always `git add -f` the
  counted artifacts, or the audit can't see them.
- **502/530 pre-arm is normal** for the opponent's endpoints until they arm; the driver waits.
- **Single recipient only** to the league (auto-send is single-recipient; separate manual sends per recipient were exercised in the friendlies).
- **Rule 52 pass:** `min_games_to_pass = 2` vs TWO DIFFERENT teams. One counted series is not
  enough for our own pass — we need a second counted game vs a different rival.
- **One-shot:** the settlement guard is the safety net; do not disable it for a counted run.
- **Role split is hardcoded** (vibecode thief-on-odd). Safe vs opponents sorting before `vibecode`
  (e.g. anrbj666); fix the split for any opponent sorting after `vibecode` before playing counted.
