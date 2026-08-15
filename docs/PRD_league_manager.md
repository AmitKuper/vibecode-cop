# PRD — league_manager

Component requirements for the `league_manager/` package: the routing facade,
series bookkeeping and Gmail reporting stack that sits around the workers.
Architecture context: `docs/DESIGN.md` (containers, AD-1, AD-7, AD-9).

## 1. Description

`league_manager` owns everything that is about the *league*, not a single move:

- **Routing** (`router.py`): `ProtocolDialectRouter` — routes inbound
  reference-v3 calls to the correct worker (cop vs thief) by sender role and
  sub-game.
- **External MCP server** (`mcp_server.py`): exposes the four reference-v3
  tools (`negotiate`, `receive_turn`, `submit_audit`, `receive_control`) to the
  peer.
- **Series lifecycle** (`series_lifecycle.py`, `series_jsonl.py`): tracks
  gamelet settlement toward series closure (exactly six sub-games); append-only
  JSONL event trail.
- **League ledger** (`league_ledger.py`): local signed append-only ledger —
  at most the allowed number of counted matches, each opponent at most once
  (rule 52); backs `results/counted_series.json`.
- **Peer topology** (`peer_topology.py`): how to reach the opponent's MCP
  server(s) — per-role URLs, static-IP/port-forward model.
- **Worker lifecycle** (`worker_lifecycle.py`): start, stop, ping cop/thief
  workers.
- **Admin API** (`admin_api.py`): localhost-only HTTP management surface.
- **Gmail pipeline** (`gmail/`): fail-closed Gatekeeper with `TokenBucket`,
  `CircuitBreaker`, `DosDetector` in front of `sender.py`.

## 2. Requirements

### Input

- Inbound reference-v3 wire messages (shapes as in `docs/PRD_cop_worker.md`
  §2 — the protocol module here mirrors `cop_worker/protocol/`, see AD-9);
  the router must dispatch on `sender` role, discarding turns from a stale
  sub-game's sender.
- Settlement events from the match path: per-sub-game outcome, audit verdict,
  running score.
- Admin requests on the localhost-only API.

### Output

- Series events appended to JSONL; ledger rows for counted results
  (`results/counted_series.json`, declarations under `results/`).
- Result emails via the Gatekeeper. Ordering is fail-closed: DoS detector →
  token bucket → circuit breaker → sender; any tripped stage withholds the send
  rather than bypassing a limit.
- Worker health state (start/stop/ping) for the lifecycle manager.

### Behavioural constraints

- A series reports only when all six sub-games are settled (rule 35 —
  `REPORT WITHHELD` otherwise).
- Counted accounting: at most one counted match per opponent; the counted
  ledger is append-only and signed.
- The counted report address is provided at run time (`--report-to`), never
  stored (see AD-7); the friendly default recipient is our own inbox.
- Admin API binds localhost only — never exposed through the router port-forward.

## 3. Constraints

- Same toolchain gates as the repo (ruff clean, pytest, branch coverage >= 94%).
- No LLM calls anywhere in this package; no network in unit tests (Gmail tested
  against mocks — `tests/test_codex_mock_gmail.py`, `test_codex_process_gmail.py`).
- Duplicated protocol modules with `cop_worker` are accepted debt (AD-9);
  mirrored `*_lm.py` test suites pin both copies to identical behaviour.

## 4. Success indicators

| Indicator | Target | Actual |
|---|---|---|
| Counted ledger integrity | 2 counted series, 2 distinct opponents | satisfied (anrbj666, imreeyal) |
| Report discipline | 0 emails on unsettled series; counted report delivered | counted report id `19fecf55c1b5eea0` |
| Gatekeeper behaviour | fail-closed under limit/anomaly | pinned by gatekeeper/circuit-breaker/token-bucket tests |
| Mirrored-suite parity | `*_lm.py` tests green | passing in the 1,891-test suite |

## 5. Test scenarios

- `tests/test_codex_router.py` — dialect routing to the correct worker.
- `tests/test_codex_series_lifecycle.py` — six-gamelet settlement and closure.
- `tests/test_codex_gmail_gatekeeper.py`, `test_circuit_breaker_ported*.py` —
  rate limiting, breaker trips, DoS withholding.
- `tests/test_codex_peer_topology.py`, `test_codex_mock_worker.py` — topology
  and worker lifecycle contracts.
- `league_manager/tests/` — package-local unit suites.
- Live-path proof: the counted series artifacts and ledger rows under
  `results/` and `evidence/game_vs_imreeyal/`.
