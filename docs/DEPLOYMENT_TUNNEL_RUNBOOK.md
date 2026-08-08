# Deployment Tunnel Runbook

**Architecture:** 3-process design (see `docs/DESIGN.md` Decisions 1–5, 19).
`vibecode-cop` is the deployable unit for a match — it provides the **LeagueManager**
and the **cop worker**. Our side plays **both** roles across the six gamelets (cop
in gamelets 1/3/5, thief in 2/4/6), so the match machine also needs the thief worker
from `vibecode-thief`.

> NETWORK STEPS ARE EXTERNAL_PENDING — they require a real public endpoint (router
> port-forward or tunnel) and a live opponent.

---

## Connection topologies — both are supported

The opponent may connect **either** way; support both:

- **A. Single LeagueManager endpoint (facade).** The peer connects to one stable URL —
  the LM on `61222`. LM terminates transport and routes each sub-game to the correct
  internal worker (single-address topology, DESIGN Decision 2). Simplest for the
  opponent: one URL for all six sub-games.
- **B. Direct to workers.** The peer connects straight to the worker MCP servers —
  cop on `61224`, thief on `61223` — with no LM in the path. This is what the local
  two-team harness `scripts/live_two_team_sim.py` uses (Group A cop `61224` /
  thief `61223`, Group B cop `61234` / thief `61233`).

Both use MCP over HTTP; the difference is only what the peer dials.

---

## Process / port map

| Process        | Repo             | Role                             | Port                                | Exposure |
|----------------|------------------|----------------------------------|-------------------------------------|----------|
| LeagueManager  | `vibecode-cop`   | external MCP facade (topology A) | `61222`                             | public (A) |
| Cop Worker     | `vibecode-cop`   | MCP server (cop role)            | `8001` internal (A) / `61224` direct (B) | internal (A) / public (B) |
| Thief Worker   | `vibecode-thief` | MCP server (thief role)          | `8002` internal (A) / `61223` direct (B) | internal (A) / public (B) |
| Admin API      | `vibecode-cop`   | localhost-only control HTTP      | `8080`                              | localhost |

Under topology A, LM auto-starts the workers on internal ports `8001`/`8002`
(`league_manager/worker_lifecycle.py`). Under topology B, the workers run standalone
on their CLI defaults `61224`/`61223`, matching the router forwards below.

---

## Prerequisites

- Match machine has **both** repos cloned and `uv sync --frozen` completed.
- Python 3.12+, uv.
- A public endpoint for whichever ports the chosen topology exposes (see below).
- Gmail OAuth configured (see `docs/GMAIL_REPORTING_RUNBOOK.md`).

---

## Exposing the endpoint

### Option 1 — Router port forwarding (current setup)

Match machine LAN IP `192.168.0.112` (static); public IP `62.56.220.143`.

| Name                 | Internal IP     | External | Internal | Used by                       |
|----------------------|-----------------|----------|----------|-------------------------------|
| `final_project_LM`   | `192.168.0.112` | `61222`  | `61222`  | topology A (LM facade)        |
| `final_project_thief`| `192.168.0.112` | `61223`  | `61223`  | topology B (direct thief)     |
| `final_project_cop`  | `192.168.0.112` | `61224`  | `61224`  | topology B (direct cop)       |

Give the opponent: `http://62.56.220.143:61222` (topology A) **or**
`http://62.56.220.143:61224` (cop) / `:61223` (thief) (topology B).

### Option 2 — Tunnel (no port forwarding)

```bash
ngrok http 61222        # topology A (LM)
# or, topology B:
ngrok http 61224        # direct cop
ngrok http 61223        # direct thief
# Cloudflare equivalent:
cloudflared tunnel --url http://localhost:61222
```

Share the public HTTPS URL(s) with the opponent.

---

## Launch

### Topology A — LeagueManager facade

```bash
cd vibecode-cop
uv run python -m league_manager --counted --port 61222 --admin-port 8080
```

LM starts, manages the cop and thief workers as internal subprocesses, and listens
for the opponent on `61222`. `--counted` enables counted-match mode and the Gmail
two-factor send guard (DESIGN Decision 30).

### Topology B — direct workers

```bash
# cop worker (this repo)
cd vibecode-cop &&  uv run python -m cop_worker  --port 61224
# thief worker (other repo)
cd vibecode-thief && uv run python -m thief_worker --port 61223
```

The opponent connects directly to each worker port for the sub-games where that role
applies.

---

## Verify results

After all six gamelets settle, both peers should:
1. Complete 6 gamelets with no TECHNICAL_LOSS.
2. Reach **signed bilateral consensus** (identical `ResultAgreement` signatures).
3. Write per-gamelet JSONL reports under the configured output dir.
4. Independently send the Gmail result report (see `docs/GMAIL_REPORTING_RUNBOOK.md`).

---

## Troubleshooting

- Timeout errors: increase the deadline-tracker timeout in config.
- Commitment mismatch: verify system clocks are NTP-synchronized.
- Peer cannot connect: confirm the exposed port (`61222` for A, `61223`/`61224` for B)
  is reachable through the forward/tunnel.
- Gmail failure: verify OAuth token refresh (see `docs/GMAIL_REPORTING_RUNBOOK.md`).
