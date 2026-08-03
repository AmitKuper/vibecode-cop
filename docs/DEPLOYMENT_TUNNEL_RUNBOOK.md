# Deployment Tunnel Runbook

NOTE: All steps below are EXTERNAL_PENDING — requires separate physical machines
and internet connectivity.

## Prerequisites

- Both machines have internet access
- Python 3.12+, uv installed on both
- ngrok account (free tier sufficient) or Cloudflare Tunnel
- Both repos cloned and `uv sync --frozen` completed
- Gmail OAuth credentials configured (see docs/GMAIL_REPORTING_RUNBOOK.md)

## Step 1 — Start Thief Agent (Machine B)

```bash
cd vibecode-thief
uvicorn agent.orchestrator_crew:app --host 0.0.0.0 --port 8000
```

## Step 2 — Expose Thief Agent via Tunnel (Machine B)

```bash
ngrok http 8000
```

Note the public HTTPS URL, e.g. `https://abc123.ngrok-free.app`.
Share this URL with the cop operator (Machine A).

## Step 3 — Start Cop Agent (Machine A)

```bash
cd vibecode-cop
uvicorn agent.orchestrator_crew:app --host 0.0.0.0 --port 8000
```

Expose cop agent similarly if thief needs to call back:
```bash
ngrok http 8000
```

## Step 4 — Run Counted Series (Machine A or either)

```bash
uv run python scripts/run_series.py \
    --counted \
    --n-gamelets 6 \
    --opponent-url https://abc123.ngrok-free.app
```

## Step 5 — Verify Results

Both agents should:
1. Complete 6 gamelets with no TECHNICAL_LOSS
2. Send Gmail reports with identical ResultAgreement signatures
3. Log final scores to `results/` directory
4. Print bilateral audit status: PASSED

## Cloudflare Alternative

```bash
cloudflared tunnel --url http://localhost:8000
```

## Troubleshooting

- Timeout errors: increase DEADLINE_TRACKER_TIMEOUT_S in config
- Commitment mismatch: check system clocks are synchronized (NTP)
- Gmail failure: verify OAuth token refresh (see GMAIL_REPORTING_RUNBOOK.md)
