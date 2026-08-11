# Evidence — COUNTED game vs uoh-sqak (vibecode COP gamelets)

Counted league series `uoh-sqak-vs-vibecode`, played 2026-08-12 01:58 Israel time
(T agreed in writing; both peers bound early and holding at sub-game 1).
This directory holds **vibecode's COP gamelets** (sub-games g02, g04, g06 — vibecode
played police) plus the series-level report shared by both repos. The vibecode THIEF
gamelets (g01, g03, g05) live in the vibecode-thief repo under the same path.

## Result (official, filed with the league)

- Winner: **vibecode** — total_score `{vibecode: 90, uoh-sqak: 30}`, sub_games_won `{vibecode: 6, uoh-sqak: 0}`
- 6/6 audits `Verified OK`; `mutual_agreement` `dfb41c7da5efc0b66d668f4a935ea04a403359ea697e21a9d2e5cad934645834`, confirmed
- `diversity_reward_applied {vibecode: true}` (winner, first counted meeting);
  `games_played_including_this {vibecode: 3, uoh-sqak: 2}` — arithmetic confirmed in
  writing by both teams before the T
- Reported to `rmisegal+uoh26finalgame@gmail.com` ALONE, message-id `19ff3140bfdfea7c`;
  counted ledger now `counted_games_played: 3`
- `game_uid e294ea6e-31c6-e5bf-0a27-1bc8e6dad89f`; scent `subtractive_chebyshev_v1`
  (lock `81ebee59640e80eae8ca9ee5f86abd26e7edf5cdbb27d15925cb6ee45ca6ddf4`)
- Clean-tree hashes exchanged in writing before the T:
  vibecode cop `5e36d072f5f10ac88e095d85c7a382c01d57e64e`,
  vibecode thief `d400dc3c8628adacd5cb1f5b031606510a968b19`,
  uoh-sqak `0ce69577cc9681526be590b891bc3bb748ddf641`

## Files

| File | Contents |
|---|---|
| `result_uoh-sqak-vs-vibecode.json` | series report (the emailed final_game_result) |
| `declaration_uoh-sqak-vs-vibecode.json` | pre-game declaration (identities, counters) |
| `counted_series.json` | counted-series ledger (`counted_games_played: 3`) |
| `config_..._g02/g04/g06.json` | config for vibecode's cop gamelets |
| `log_..._g02/g04/g06.json` | sealed step-0 + move records + mutual audit for vibecode's cop gamelets |
| `report_vibecode_to_lecturer_19ff3140bfdfea7c.eml` | the actual report email filed to the league (From agentsorch@gmail.com → rmisegal+uoh26finalgame@gmail.com); its result JSON matches this evidence byte-for-byte |
| `report_uoh-sqak_copy_received.eml` | uoh-sqak's forward of THEIR lecturer report (original To rmisegal+uoh26finalgame@gmail.com at 02:06) — rule-35 agreement verified: all pair-observable fields identical, same mutual_agreement sha |
| `runtime_match.log` | full wire log of the counted run (bind 01:58:00, six settled windows, no holds/retries) |

## Context

Three complete friendly series preceded this counted game the same night, all
won 90-30 with 6/6 audits and byte-identical §5b signatures (identical outcomes
and game_uid make the counted series' signature equal the friendlies' — same
preimage by construction). Both teams' report paths were proven on friendlies
before the counted window, per the jointly agreed gate.
