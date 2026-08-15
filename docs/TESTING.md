# TESTING — strategy and taxonomy (vibecode-cop)

Status: current as of 2026-08-15. Companion evidence document:
`docs/TEST_EVIDENCE.md` (what the suite measured, when, and at which SHA).

## How to run

```bash
# The suite CI gates (tests/ + the two package-local suites)
uv run pytest tests/ cop_worker/tests/ league_manager/tests/ -q --tb=short

# The exact coverage gate from .github/workflows/ci.yml
uv run pytest tests/ cop_worker/tests/ league_manager/tests/ \
  --cov=cop_worker --cov=league_manager --cov-branch \
  --cov-report=xml \
  --cov-fail-under=94
```

CI (`.github/workflows/ci.yml`) additionally enforces: `uv sync --frozen`,
`uv lock --check`, `ruff check .`, `ruff format --check .`, and a secret scan over
`*.py`/`*.json`. Coverage is **branch** coverage (stricter than line) and is
enforced twice: on the CI command line and via `fail_under = 94` in
`pyproject.toml [tool.coverage.report]`.

**Gate: 94% branch** — well above the course guideline floor of 85. The suite
last measured **94.90%** (see `docs/TEST_EVIDENCE.md`); the gate is raised only
by adding tests, never by changing source for coverage's sake.

## Test taxonomy — what actually exists

The suite is not one kind of test. Five distinct species, each with a different
failure it is designed to catch:

### 1. Unit tests
Plain behavior tests of a module in isolation: domain transition and rules
(`tests/test_cov95_rules_outcomes.py`, `tests/test_coverage_gaps_domain.py`,
`tests/test_codex_scent_grid.py`), crypto and commit-reveal
(`tests/test_codex_crypto.py`, `tests/test_codex_commit_reveal.py`,
`tests/test_audit_adversarial_consensus.py`,
`tests/test_audit_adversarial_journal.py` — step-journal hash-chain tamper,
insert, delete, zero-turn abort; bilateral result consensus), the Gmail pipeline
(gatekeeper/token-bucket/circuit-breaker/DoS-detector tests), config canonicalization,
the RL observation/policy stack.

### 2. Protocol conformance against the league kit's pinned vectors
The external kit (`copthief-league-protocol`) publishes byte-exact fixtures; we port
them **verbatim** into our tests so conformance is checked on every run without
importing the kit:

- `tests/test_scent_chebyshev.py` — fixture values copied from the kit's
  `vectors/pheromone.json` (CORE; in a sibling checkout,
  `../external/copthief-league-protocol/vectors/pheromone.json`) at kit commit
  `be96e57`; fails if our
  `cop_worker/scent_chebyshev.py` port ever drifts from the reference arithmetic.
- `tests/reference_v3/test_game_uid_vectors.py` — game-uid derivation vectors.
- `tests/test_scent_model_negotiation.py` — pins that `SCENT_LOCKS` carries exactly
  the kit-recomputed hashes for both scent models and that Step-0 puts the locked
  hash on the wire.

The full kit vector run (`verify_vectors.py`: 125 checks / 15 fixtures) is executed
out-of-band by `scripts/verify_reference_v3_interop.py` against an unmodified kit
checkout — see `docs/TEST_EVIDENCE.md`.

### 3. Source-inspection call-site pins
A lesson bought at match cost: **a correct method proves nothing if the serving loop
never calls it.** These tests use `inspect.getsource()` on the production entry point
(`scripts/live_match_ref3.py`) and assert the *call sites and their ordering*:

- `tests/test_serving_episode_reset.py::test_play_subgame_resets_the_mover_before_the_first_turn`
  — asserts `policy.reset()` appears **after** the `RLMover(` construction and
  **before** the turn loop in `_run_turns` (the facade re-exports it from
  `scripts/ref3_match/subgame_turns.py` precisely for this pin).
- `tests/test_thief_enclosure_concession.py::TestServingLoopCallSites` — asserts the
  loop calls `observe_peer_barrier` and `self_capture_check`, and that the
  concession turn (with `"caught": True`, an advancing scent field, and `"move": "STAY"`)
  precedes `send_audit`.

These are deliberately brittle in one direction: refactoring the loop is allowed to
break them, silently deleting the behavior is not.

### 4. Live-found-bug regression tests (the TDD-ish loop)
The working discipline is **bug observed live → pinning test written → fix → test
stays forever**. Each such test documents its incident in the module docstring.
Real examples:

| Test | Live incident it pins |
|---|---|
| `tests/test_serving_episode_reset.py` | GRU hidden state carried across sub-games — `_play_subgame` built an `RLMover` and never called `policy.reset()`; the net played sub-games 2–6 "mid-thought" through counted games without any loud failure. Also pins the worker path (`cop_worker/mcp_server.py::start_playing` resets the shared module-level `_POLICY`). |
| `tests/test_thief_enclosure_concession.py` | Rule-46/47 enclosure is an ending only the thief can see; a thief that plays on claims a survival the cop's audit scores as a capture — two honest teams, contradictory reports, rule 35 zeroes both. Born from a live hazard identified before the imreeyal pairing. |
| `tests/test_turn_timestamp.py` | The empty-timestamp match-ender: a turn with `timestamp: ""` was refused by a strict peer, ending a friendly. Pins non-empty ISO-8601 stamps, that `""` is replaced rather than sent, and that the stamp stays out of the commit preimage (re-sends must re-seal identically). |
| `tests/test_cop_capture_claim.py` | Our cop only ever *answered* concessions — it never emitted `capture_claim`, so against a thief that also only answers, no co-location capture could settle in either direction. Also pins corroboration: a `caught=true` is checked against OUR barrier record; failure records a *disputed* capture. |
| `tests/reference_v3/test_duplicate_turn_idempotency.py`, `test_conflicting_duplicate_rejected.py` | At-least-once retries require dedup-on-commit: a re-send with identical bytes is drained, a re-send under a NEW commit (equivocation) is refused. |

### 5. Coverage-gap and contract tests
Named `test_codex_*` / `test_cov85_*` / `test_cov90_*` / `test_cov95_*` /
`test_coverage_gaps_*.py`: written specifically
to close measured branch-coverage gaps or to pin narrow API contracts
(fail-closed token accounting, empty tool lists, recurrent-policy failure modes).
They raise the floor; they are not the primary defect-finding species.

### Mirrored suites (duplication watchdog)
`cop_worker/` and `league_manager/` still carry copies of some modules (see
`docs/DESIGN.md` AD-9). Where a copy exists, its tests exist twice too — the `_lm`
variants (`tests/test_codex_adaptive_transport.py` ↔ `..._lm.py`,
`tests/test_capability_negotiation_ported.py` ↔ `..._lm.py`, `tests/test_league_ledger_lm.py`,
…) — so any drift between the copies fails a build instead of surfacing on the wire.
Where the copy was collapsed into a module alias (`league_manager/gmail/*`,
`league_manager/protocol/dsl.py`, …) the aliased test still runs against the alias.

## Edge-case policy — null / empty / boundary

Every wire-facing input is tested at the boundary and below it, because the peer is
another student team and the audit is unforgiving. Live examples in `tests/`:

- **Empty / null:** `test_turn_timestamp.py::test_empty_string_is_replaced_rather_than_sent`;
  `test_codex_adaptive_transport.py::test_protocol_detection_error_is_raised_on_empty_tool_list`;
  `test_codex_recurrent_failure_contract_policy.py::test_policy_rejects_empty_and_undeployable_legal_masks`.
- **Junk / wrong type:** `test_thief_enclosure_concession.py::test_duplicates_and_out_of_board_and_junk_ignored`
  — feeds `None`, the string `"2,3"`, duplicates, and the off-board cell `[9, 9]` to
  `observe_peer_barrier` and asserts none of them poison the barrier list.
- **Boundary:** `tests/reference_v3/test_sub_game_validation.py::test_sub_game_number_out_of_range_rejected`;
  `test_codex_scent_grid.py::test_scent_out_of_bounds_is_zero`;
  `test_rl_pure_helpers.py::test_apply_place_action_noop_off_board`;
  `test_mcp_coordinator.py::test_inbound_commit_out_of_order_rejected`.
- **Malformed adversarial:** `test_cop_capture_claim.py::test_malformed_cell_is_disputed`
  — a malformed capture cell records a dispute, never a clean settlement.

The rule of thumb: anything that arrives from the peer gets a junk test, a boundary
test, and an ordering test; anything that leaves for the peer gets a "cannot send
the broken shape" test.

## Skips

Four tests skip, all on an environment condition, never on a defect:

- `tests/reference_v3/test_survival_terminal.py` — `thief_worker not on path`; it
  exercises the cross-repo survival terminal and runs only when the sibling
  `vibecode-thief` checkout is importable.
- `tests/test_pdf_parser_docx.py` (2) and `tests/test_submission_builder.py` (1) —
  `python-docx not installed in this venv`; they cover the `tools/` submission
  helpers, which are not part of the match runtime.

Everything else must pass; `addopts`-level permanent ignores are not used in this
repo.
