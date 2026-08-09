# `config/` — vibecode-cop configuration

Every main parameter for a game lives here. Two kinds of config, one hashed and one not.

```
config/
├── game.json         # SHARED CONSTITUTION — hashed (config_sha256). Single source of truth
│                     #   for ALL game parameters (board, scent, scoring, movement, league).
├── runtime.toml      # PRIVATE runtime params — NOT hashed (network, timeouts, llm, identity, report).
├── README.md         # this file
├── opponents/        # saved per-opponent profiles (auto-written after each game)
│   └── <group>/{game.json, runtime.toml}
└── games/            # generated config artifacts per sub-game (output; like results/)
```

## What is part of the SHA

There are two file-derived hashes exchanged with the opponent. **Only `game.json` feeds them.**
`runtime.toml` is never hashed and never shared.

### `config_sha256` — whole-file hash of `game.json`

- **Value (vs anrbj666):** `9ed3b2e9601d3378b838740edadf03ad12ff17adefead7d18397de68cf860c23`
- **Preimage:** `sha256(canonical(WHOLE game.json))`, canonical =
  `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",",":"))`.
- **Code:** `scripts/ref3_artifacts.py::config_sha256()`.
- **Scope = every section of `game.json`** (a subset would defeat rule 11):

| game.json section | keys |
|---|---|
| top-level | `schema_version`, `agreed_between` |
| `board_and_agents` | grid_size, num_agents, thief_start, cop_start, axis_origin_corner, axis_start_index |
| `world` | map_area, hint_max_words |
| `movement_and_barriers` | move_set, max_barriers, max_moves, survival_threshold |
| `scoring` | capture_cop, capture_thief, survival_cop, survival_thief, tie_score, technical_loss |
| `pheromones` | pheromone_center_intensity, pheromone_decay, pheromone_grid_size, min_center_intensity |
| `network_and_league` | response_timeout_sec, watchdog_timeout_sec, num_games, diversity_reward, min_games_to_pass, max_games_per_team, token_budget_per_series |
| `rate_limiter_gatekeeper` | requests_per_minute, concurrent_requests, retry_backoff_sec, max_retries, queue_depth |

### `game_uid` — identity hash (derived from `game.json`, not stored)

- **Value (vs anrbj666):** `b2a16946-2cad-909f-60aa-b0cc8a8b7c4f`
- **Preimage:** `UUID(sha256(canonical(TERMS) + "|" + "|".join(sorted(pair)))[:16])`.
- **TERMS** = the 14 reference-v3 keys, **derived from `game.json`** via
  `reference_v3.terms_from_game()` (board_size, smell_grid_size, decay_per_step, emit_intensity,
  min_center_intensity, max_steps, barriers_max, setting, hint_max_words, axis_origin_corner,
  axis_start_index, thief_start, cop_start, num_games). `game.json` is the single source, so the
  wire terms, `config_sha256`, and the physics cannot drift. A drift-guard test enforces this.

### Locked model hashes (constants, not file-derived)

| hash | value | source |
|---|---|---|
| `scent_model_sha256` | `934c220d…` | `reference_v3.REFERENCE_V3_SCENT_LOCK` |
| `wire_shape_sha256` | `229ae648…` | `reference_v3.REFERENCE_V3_WIRE_LOCK` |

## What is NOT hashed — `runtime.toml`

`[network]` ports/URLs/opponent, `[timeouts]`, `[llm]`, `[identity]` (group/members/repos),
`[report]` recipient/mode/token, `[counted]` counted_played. Edit freely — it changes how we
run, not the game rules. **The league/counted report address is never stored here; it is passed
explicitly at run time (`--report-to`) for a counted game only.**

## Selecting a config (`--config`)

```
python scripts/live_match_ref3.py --match --config anrbj666 ...
```
- `--config <name>` → `config/opponents/<name>/` if it exists, else the base `config/`.
- `--config <dir>` → that directory.
- default → base `config/`.
- CLI flags always override profile values.

## Per-opponent save

After each match, the effective `game.json` + `runtime.toml` are copied to
`config/opponents/<opponent_group>/` — an auditable record and a reusable profile for next time.
