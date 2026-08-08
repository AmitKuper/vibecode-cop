# Deployment Tunnel Runbook

**Architecture:** 3-process design (see `docs/DESIGN.md` Decisions 1–5, 19).
`vibecode-cop` is the deployable unit for a match — it runs the **LeagueManager**,
the single external-facing MCP endpoint. Our side plays **both** roles across the
six gamelets (cop in gamelets 1/3/5, thief in 2/4/6), so the match machine needs
both the cop worker (from `vibecode-cop`) and the thief worker (from
`vibecode-thief`).

> NETWORK STEPS ARE EXTERNAL_PENDING — they require a real public endpoint (router
> port-forward or tunnel) and a live opponent.

---

## Process topology

| Process        | Repo             | Role                             | Port                         | Exposure  |
|----------------|------------------|----------------------------------|------------------------------|-----------|
| LeagueManager  | `vibecode-cop`   | single external MCP endpoint     | `61222`                      | PUBLIC    |
| Cop Worker     | `vibecode-cop`   | internal MCP server (cop role)   | `8001` internal / `61224` standalone | internal |
| Thief Worker   | `vibecode-thief` | internal MCP server (thief role) | `8002` internal / `61223` standalone | internal |
| Admin API      | `vibecode-cop`   | localhost-only control HTTP      | `8080`                       | localhost |

The opponent connects to **one** URL — the LeagueManager on `61222`. LM terminates
transport and routes each sub-game to the correct internal worker; the workers own
all game semantics (single-address topology, DESIGN Decision 2). When LM auto-starts
the workers it launches them on internal ports `8001`/`8002` (`league_manager/worker_lifecycle.py`);
the `61223`/`61224` numbers are the workers' standalone CLI defaults, matching the
router forwards below.

---

## Prerequisites

- Match machine has **both** repos cloned and `uv sync --frozen` completed.
- Python 3.12+, uv.
- A public endpoint for `LM:61222` — either the router port-forward (Option A) or a
  tunnel (Option B).
- Gmail OAuth configured (see `docs/GMAIL_REPORTING_RUNBOOK.md`).

---

## Option A — Router port forwarding (current setup)

Match machine LAN IP `192.168.0.112` (static); public IP `62.56.220.143`.

| Name                 | Internal IP     | External | Internal | Notes                     |
|----------------------|-----------------|----------|----------|---------------------------|
| `final_project_LM`   | `192.168.0.112` | `61222`  | `61222`  | peer connects here        |
| `final_project_thief`| `192.168.0.112` | `61223`  | `61223`  | thief worker (standalone) |
| `final_project_cop`  | `192.168.0.112` | `61224`  | `61224`  | cop worker (standalone)   |

Give the opponent: `http://62.56.220.143:61222`

## Option B — Tunnel (no port forwarding)

```bash
ngrok http 61222
# or
cloudflared tunnel --url http://localhost:61222
```

Share the public HTTPS URL with the opponent.

---

## Launch

```bash
cd vibecode-cop
uv run python -m league_manager --counted --port 61222 --admin-port 8080
```

LeagueManager starts, manages the cop and thief workers as internal subprocesses,
and listens for the opponent on `61222`. `--counted` enables counted-match mode and
the Gmail two-factor send guard (DESIGN Decision 30).

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
- Peer cannot connect: confirm `LM:61222` is reachable through the forward/tunnel.
- Gmail failure: verify OAuth token refresh (see `docs/GMAIL_REPORTING_RUNBOOK.md`).
