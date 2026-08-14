# Evidence — COUNTED game vs rstabcde (vibecode COP gamelets)

Counted league series `rstabcde-vs-vibecode`, played 2026-08-14 18:26 Israel time
(T = 18:26 agreed in writing; preceded by three fully-reconciled friendlies the
same day, all 90-30). This directory holds **vibecode's COP gamelets** (sub-games
g02, g04, g06 — vibecode played police) plus the series-level report shared by
both repos. The vibecode THIEF gamelets (g01, g03, g05) live in the
vibecode-thief repo under the same path.

## Result (official, filed with the league)

- Winner: **vibecode** — total_score `{vibecode: 90, rstabcde: 30}`, sub_games_won
  `{vibecode: 6, rstabcde: 0}` (all three cop gamelets: capture at step 13-14)
- 6/6 audits `Verified OK`; `mutual_agreement`
  `b220c6364f1677c7a46b9df3bece47ebb6ea494d03fae31360ab9504fa4ab6d4`, confirmed —
  **identical sha independently computed in rstabcde's league report** (standard
  ADR-0012 preimage, adopted by rstabcde after the 17:20 friendly)
- `diversity_reward_applied {vibecode: true}` (winner, first counted meeting);
  `games_played_including_this {vibecode: 4, rstabcde: 1}`
- Reported to `rmisegal+uoh26finalgame@gmail.com` ALONE, message-id
  `1a000e76ccd62963`; counted ledger now `counted_games_played: 4`
- `game_uid 2ea82ca8-0249-e839-d19a-c749f9408652`; scent `subtractive_chebyshev_v1`
  (lock `81ebee59640e80eae8ca9ee5f86abd26e7edf5cdbb27d15925cb6ee45ca6ddf4`)
- Declared commits at Step-0: cop `76bf6d7`, thief `242fc00` (both pushed pre-T)

## Files

- `config_… / log_…_g{02,04,06}.json` — the three police gamelets (this repo's role)
- `declaration_… / result_….json` — series-level artifacts (identical in both repos)
- `counted_series.json` — ledger snapshot after filing (4 counted series)
- `report_vibecode_to_lecturer_1a000e76ccd62963.eml` — byte-exact from our Sent box
- `report_rstabcde_copy_received.eml` — their league report, forwarded to us
  2026-08-14 18:37 (their original sent 18:34 to the league address); attachment
  reconciled: winner/score/all six rows/mutual sha all identical to ours
- `runtime_match.log` — full orchestrator log (split architecture, 18:26:25-18:32:43)

## Known peer quirks (accepted, non-blocking)

- rstabcde's capture concession carries `caught=true` without the capture cell —
  recorded as a disputed-capture marker each cop window; audits reconcile regardless.
- Their tunnels host one door at a time (bounced per window); absorbed by the
  orchestrator's per-window peer-endpoint wait.
