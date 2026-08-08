# Evidence — COUNTED game vs anrbj666 (vibecode COP gamelets)

Counted league series `anrbj666-vs-vibecode`, played 2026-08-08 22:14 Israel time.
This directory holds **vibecode's COP gamelets** (sub-games g02, g04, g06 — vibecode played
police) plus the series-level report shared by both repos. The vibecode THIEF gamelets
(g01, g03, g05) live in the vibecode-thief repo under the same path.

## Result (official, filed with the league)

- Winner: **anrbj666** — total_score `{vibecode: 35, anrbj666: 75}`, sub_games_won `{vibecode: 1, anrbj666: 5}`
- 6/6 audits `Verified OK`; `mutual_agreement` `b4db10c24e330682393c6d3dea432de040f93116710851bf8e41f6ac5c3ae67d`, confirmed
- `diversity_reward_applied {anrbj666: true}` (winner, first counted meeting); `games_played_including_this {vibecode: 1, anrbj666: 2}`
- Reported to `rmisegal+uoh26finalgame@gmail.com`, message-id `19fe2cdea7a51125`
- `game_uid b2a16946-2cad-909f-60aa-b0cc8a8b7c4f`; `config_sha256 9ed3b2e9601d3378b838740edadf03ad12ff17adefead7d18397de68cf860c23`

## Files

| File | Contents |
|---|---|
| `result_anrbj666-vs-vibecode.json` | series report (the emailed final_game_result) |
| `declaration_anrbj666-vs-vibecode.json` | pre-game declaration (identities, counters) |
| `counted_series.json` | counted-series ledger (`counted_games_played: 1`) |
| `config_..._g02/g04/g06.json` | config for vibecode's cop gamelets |
| `log_..._g02/g04/g06.json` | sealed step-0 + move records + mutual audit for vibecode's cop gamelets |
| `report_email_anrbj666-vs-vibecode.eml` | the actual report email filed to the league (From agentsorch@gmail.com → rmisegal+uoh26finalgame@gmail.com, msg-id 19fe2cdea7a51125); its result JSON matches this evidence field-for-field |

Cop gamelets outcomes: g02 survival, g04 survival, g06 survival (thief survived each; cop stops
at the survival terminal, 34 moves). Tagged `game_vs_anrbj666`.
