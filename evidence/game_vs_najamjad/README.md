# Evidence — COUNTED game vs najamjad (vibecode COP gamelets)

Counted league series `najamjad-vs-vibecode`, played 2026-08-14 21:59 Israel time
(T = 22:00 agreed in writing; preceded the same evening by three friendlies, the
last two fully reconciled in both directions). This directory holds **vibecode's
COP gamelets** (sub-games g02, g04, g06 — vibecode played police) plus the
series-level artifacts shared by both repos. The vibecode THIEF gamelets (g01,
g03, g05) live in the vibecode-thief repo under the same path.

## Result (official, filed with the league)

- Winner: **vibecode** — total_score `{vibecode: 90, najamjad: 30}`, sub_games_won
  `{vibecode: 6, najamjad: 0}` (three cop captures at step 13, three thief survivals
  at the full 35 steps)
- 6/6 audits `Verified OK`; `mutual_agreement`
  `041880e56de2349cf23f20ea20b713891a249fbecb1e2703809cda06458ec790`, confirmed —
  **the same digest najamjad computed independently**, and confirmed=true on BOTH
  sides (see the reconciliation note below)
- `diversity_reward_applied {vibecode: true}` (winner, first counted meeting);
  `games_played_including_this {vibecode: 5, najamjad: 3}`;
  `tokens_total_series {vibecode: 0, najamjad: 0}`
- Reported to `rmisegal+uoh26finalgame@gmail.com` ALONE, message-id
  `1a001a7f77c911c3`; counted ledger now `counted_games_played: 5`
- `game_uid eb6ddfa3-6dde-836d-78d5-8c4e8e2d1372`; scent `subtractive_chebyshev_v1`
  (lock `81ebee59640e80eae8ca9ee5f86abd26e7edf5cdbb27d15925cb6ee45ca6ddf4`)
- Frozen commits declared at Step-0, exchanged in writing before T:
  vibecode cop `6c3ea00d33ece171c0c7a8c5fd8eff52ac677992`,
  vibecode thief `8dc9ff66094a0aa9c1f87ae8c8625c1a88c63b32`;
  najamjad cop `f80d07cbfacc49b2763bd9e1ea710c1b61a2ce2a`,
  najamjad thief `57e186f177340ee90b733b1ccc96222e7f7a5ad5`

## Why this pairing is unusually well evidenced

najamjad audit their opponent after every match and published their findings on
us. Three were real defects in this codebase and were fixed BEFORE this counted
series (all with tests, all in the code that played it):

1. `hardware_spec` was empty in every game ever played — the builder imported
   psutil (absent from the runtime venv) inside a broad `except`. Now stdlib-only
   and carried in the sealed step-0 record under `spec`.
2. Our declared counted count was stale (3 vs the ledger's 4).
   `opponents_already_counted` is now derived live from the ledger.
3. **The one that mattered:** our audit `result_claim` said `timeout` when the
   thief outlasted the step limit, contradicting our own result row's `survival`.
   najamjad's dispute rule flagged it, and their `mutual_agreement.confirmed` came
   out false while ours said true — the rules 33-35 shape that voids a match.
   Fixed (`result_claim()`, pinned by tests/test_result_claim_survival.py); the
   following friendly and this counted series both show confirmed=true on both sides.

## Files

- `config_… / log_…_g{02,04,06}.json` — the three police gamelets (this repo's role)
- `declaration_… / result_….json` — series-level artifacts (identical in both repos)
- `counted_series.json` — ledger snapshot after filing (5 counted series)
- `report_vibecode_to_lecturer_1a001a7f77c911c3.eml` — byte-exact from our Sent box
- `report_najamjad_friendly_prior_reconciled.json` — najamjad's report for the
  immediately preceding friendly, reconciled field-by-field against ours (identical
  rows, identical mutual sha, confirmed=true both sides). Kept because it is the
  evidence that the claim fix works from THEIR side, not just ours.
- `runtime_match.log` — full orchestrator log (split architecture, 21:59:38-22:03:00)
