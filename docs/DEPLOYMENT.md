# DEPLOYMENT — production match deployment (vibecode-cop)

This is the deployment guide for how counted and friendly series are **actually**
played: one match-runner process on a machine behind a **static public IP with
router port-forwarding**. The LeagueManager-facade + tunnel topology is the
*alternative*, kept in `docs/DEPLOYMENT_TUNNEL_RUNBOOK.md`.

Both counted games (vs anrbj666 2026-08-08, vs imreeyal 2026-08-10) were played
exactly as described here.

## Topology

One OS process — `scripts/live_match_ref3.py --match` — serves **both** of our MCP
endpoints and dials the opponent's:

| Endpoint | Port | Forwarded |
|---|---|---|
| Our **cop** MCP endpoint | **61224** | router `61224 → 61224` (`final_project_cop`) |
| Our **thief** MCP endpoint | **61223** | router `61223 → 61223` (`final_project_thief`) |

Match machine: LAN `192.168.0.112` (static lease), public IP `62.56.220.143`.
The opponent dials `http://62.56.220.143:61224/mcp` (our cop) and
`…:61223/mcp` (our thief). Remember the crossing: **their cop talks to our thief
endpoint (:61223), their thief to our cop endpoint (:61224)**.

## Prerequisites

1. **Both repos cloned side-by-side** (`vibecode-cop/`, `vibecode-thief/`) — the
   runner loads the thief champion from the sibling repo.
2. **Frozen environments:** `uv sync --frozen` in each repo (CI also verifies
   `uv lock --check`).
3. **Gmail OAuth:** `secrets/gmail/credentials.json` + `secrets/gmail/token.json`
   (gitignored). First-time setup `uv run python scripts/setup_gmail_oauth.py`;
   verify with `uv run python scripts/verify_gmail_oauth.py`. Runbook:
   `docs/GMAIL_REPORTING_RUNBOOK.md`.
4. **Opponent profile:** `config/opponents/<opponent>/` holding the agreed
   `game.json` (hashed, exchanged with the opponent) and `runtime.toml` (private:
   URLs, ports, timeouts). Selected with `--config <opponent>`; after every match
   the effective config is saved back to the profile. See `config/README.md`.
5. **Models:** `models/MANIFEST.json` SHA-pins the champions; the obs-mode guard
   refuses to load a checkpoint whose recorded `obs_mode` contradicts the live
   `COPTHIEF_*` environment. Do not export stray `COPTHIEF_*` vars — the fix is
   always the env, never the guard.
6. **Router forwards** 61223/61224 in place; from an outside network,
   `curl -I http://62.56.220.143:61224/mcp` must answer **406** (see T-protocol).

## Launch

Friendly (default: result email goes to our own inbox, no counters touched):

```bash
cd vibecode-cop
uv run python scripts/live_match_ref3.py --match --config imreeyal
```

Counted — identical, plus exactly three deltas:

```bash
uv run python scripts/live_match_ref3.py --match --config imreeyal \
  --report-to "<LEAGUE_REPORT_ADDRESS>" \
  --counted --counted-played <N_already_played> \
  --members "Ron Marom,Amit Kuperminz"
```

- The league address is **stored nowhere** in the repo (test-enforced,
  `tests/test_config_single_source.py`); it is typed at launch, single recipient.
- Explicit flags (`--opp-cop-url`, `--opp-thief-url`, `--opponent-group`,
  `--scent-model`, `--move-policy`) override the profile when needed.
- For a timed start, use a small file-based launcher script that sleeps until T and
  then execs the command — not an inline `bash -c` one-liner.

Full pre-game checklist (constitution reconciliation, lock hashes, artifact swap
standard): `docs/counted_game_checklist.md`.

## The T-protocol (window discipline)

A series runs in agreed windows starting at a written time **T**. Summary — the full
log-signature → instruction table lives at the workspace level in
`docs/MATCH_DIAGNOSIS_PLAYBOOK.md`:

- **Before T, probe the opponent** (and have them probe us): a bare HTTP request to
  `http://<host>:<port>/mcp` answering **406 = READY** (an MCP server refusing a
  bare GET). **502** = their edge is up but no peer process is bound behind it;
  **530** = tunnel up, origin dead; **404 + ERR_NGROK_3200** = their tunnel client
  itself is gone.
- **Never debug inside a window.** If a sub-game window fails: kill the process,
  diagnose from the stamped log, agree a **new T** in writing.
- Every instruction to the other team cites our own timestamped log line
  (`reports/ref3_matches/match_<opp>_<ts>.log`: `[match]`, `[wire<-]`, `[diag]`).
- The runner **withholds the report** (settlement guard) unless all six sub-games
  settled — a half-played series files nothing, per rule 35.

## Stray-process hygiene

The runner performs a **port-free preflight** and refuses to start if 61223/61224 is
already held — a stray process from an earlier attempt would silently swallow the
peer's traffic while our own run fails in a background task. Before every window:

```powershell
Get-NetTCPConnection -LocalPort 61223,61224 -State Listen |
  ForEach-Object { Get-Process -Id $_.OwningProcess }
# kill anything found, then relaunch
```

Also close previous GUI/replay processes and any earlier `live_match_ref3` attempt.
If the preflight refuses, that is the guard working — kill the stray, don't change
the port.

## Where the run's evidence lands

| Artifact | Contents |
|---|---|
| `artifacts/` | league-schema config / declaration / log / result JSON per game |
| `reports/ref3_matches/match_*.log` | wall-clock-stamped wire log (the diagnosis source) |
| `reports/ref3_matches/last_match_result.json` | full internal snapshot incl. both audit sides |
| `results/counted_series.json` | the counted ledger |
| `config/opponents/<opp>/` | effective config saved back per opponent |

A counted series' artifacts are then copied under `evidence/game_vs_<opp>/`
(see `evidence/game_vs_imreeyal/README.md` for the format).

## Alternative: tunnel topology

If no router control or public IP is available, the older
**LeagueManager-facade + tunnel** topology still works: one public URL (LM on
61222, ngrok/cloudflared in front), workers auto-started on internal ports. That
runbook — including the direct-worker variant over a tunnel — is kept as
`docs/DEPLOYMENT_TUNNEL_RUNBOOK.md`. It is the fallback, not the production path;
port numbers there agree with this document (cop 61224 / thief 61223 / LM 61222).
