# Evidence — COUNTED game vs nis-yar1 (vibecode COP gamelets)

Counted league series `nis-yar1-vs-vibecode`, played 2026-08-16 22:32 Israel time
(T = 22:35 agreed in writing; fired at 22:32 by mutual "fire when probed").
Preceded the same evening by three friendlies (21:10, 21:52, 22:06) that were
used deliberately as a hardening loop — see below. This directory holds
**vibecode's COP gamelets** (g02, g04, g06 — vibecode played police); the THIEF
gamelets (g01, g03, g05) live in the vibecode-thief repo under the same path.

## Result (official, filed with the league)

- Winner: **vibecode** — total_score `{vibecode: 90, nis-yar1: 30}`, sub_games_won
  `{vibecode: 6, nis-yar1: 0}` (three thief survivals at the full 35 steps, three
  cop captures)
- 6/6 audits `Verified OK`; `mutual_agreement`
  `4e4950376d6adea2bda706f6614c4c34ac0111d4add4534b0d2bf39534135c98`, confirmed —
  the same digest both sides computed for the evening's clean friendlies
- `diversity_reward_applied {vibecode: true}` (winner, first counted meeting);
  `games_played_including_this {vibecode: 6, nis-yar1: 2}` — byte-agreed in
  writing before T; `tokens_total_series {vibecode: 0, nis-yar1: 0}`
- Reported to `rmisegal+uoh26finalgame@gmail.com` ALONE, message-id
  `1a00c1363a39a870`; counted ledger now `counted_games_played: 6`
- `game_uid 21a1533b-5750-edcb-ea18-35061243b3f3`; scent `subtractive_chebyshev_v1`
  (lock `81ebee59640e80eae8ca9ee5f86abd26e7edf5cdbb27d15925cb6ee45ca6ddf4`)
- Frozen commits exchanged in writing before T:
  vibecode cop `fdd15bf593e87eba925a44d0d48dd8f31a9d1810`,
  vibecode thief `542eb9337ff1b9a4a6ffdf1e54c36d014fbe75ea`;
  nis-yar1 `c6b8aa6fa5eb24dba4fedfb5f2dc5541b7a1c926` (their update from
  `324c5a37…`, sent before T per the agreed rule)

## Why this series is the strongest evidence of the fault-tolerance stack

nis-yar1's role processes exit right after their own last window, taking their
cloudflared tunnel down in the SAME MILLISECOND as the final audit. On 12/08 and
again at 21:52 on 16/08 that cost a verified window: the settled row was built
and then discarded with the teardown exception, the series filed 5/6, and the
settlement guard (correctly) withheld the report.

`scripts/ref3_match/settled_row.py` (cop `37e0ed4`) fixed that path: the row is
stashed the instant the audit verifies, and the worker's exception handler
reports the settlement with the error recorded beside it. In THIS counted series
the failure fired **twice** — their cop after g05, their thief after g06 — and
both windows survived:

```
[tw] sg5 settled, then HTTPStatusError: 502 Bad Gateway ... — reporting the settlement
[pw] sg6 settled, then HTTPStatusError: 502 Bad Gateway ... — reporting the settlement
STATUS: audits 6/6 ok
```

Without the fix this counted game would have settled 4/6 and no report could
have been filed. The rows carry `post_settlement_error` so the noise is recorded,
not hidden.

Two more cross-team fixes proven live tonight before counting:
- Their Step-0 identity now carries `github_commit` + `counted_games_played`, and
  our reader (`league_artifacts/opponent_facts.py`) harvests them from the
  identity or the sealed record — both files agree on
  `games_played_including_this` and record real commits, no "unknown".
- Their reporting is single-emitter and their auto-send was DISABLED for the
  counted run: exactly one report per team, sent only after mutual 6/6
  confirmation — the no-settlement-no-email rule both sides agreed in writing.

## Files

- `config_… / log_…_g{02,04,06}.json` — the three police gamelets (this repo's role)
- `declaration_… / result_….json` — series-level artifacts (identical in both repos)
- `counted_series.json` — ledger snapshot after filing (6 counted series)
- `report_vibecode_to_lecturer_1a00c1363a39a870.eml` — byte-exact from our Sent box
- `runtime_match.log` — full orchestrator log (split architecture, 22:32:42-22:36:33)
- `report_nis-yar1_copy_received.eml` + `report_nis-yar1_counted_result.json` —
  their league report (inner To: the league address alone), forwarded to us
  22:48 IST, Gmail id `1a00c1eac3363080`. Reconciled field-by-field: identical
  `mutual_agreement.sha256` and confirmed, all six rows, all counters, and both
  files record the same three frozen commits.
