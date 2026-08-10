# PRD — cop_worker

Component requirements for the `cop_worker/` package: the cop-side agent library
that the match runner (`scripts/live_match_ref3.py`) composes into a live series.
Architecture context: `docs/DESIGN.md`. Move-engine theory: `docs/PRD_search_engine.md`.

## 1. Description

`cop_worker` provides everything the cop needs to play a reference-v3 sub-game:

- **Protocol** (`cop_worker/protocol/`): reference-v3 wire — canonical JSON,
  commit construction, terms/locks, session state, turn/audit validation, plus
  the pre-game protocol-understanding agent and dialect introspection.
- **Domain** (`board.py`, `rules_engine.py`, `gamelet.py`, `observation.py`):
  canonical 7x7 physics, rule outcomes (capture, rule-46 place-onto-thief,
  rule-47 enclosure, survival), `LocalObservation`/`BeliefState` with no hidden
  coordinates.
- **Move engine** (`rl/`): minimax search over exact chebyshev tracking with a
  manifest-pinned RL fallback, behind one `select_action` seam.
- **Scent** (`scent.py`, `scent_chebyshev.py`): byte-exact emission for both
  registered scent laws; what we transmit is what the law prescribes.
- **Language** (`language/`): free-text hints with a deception policy, LLM or
  template backed — provably decoupled from movement (`docs/PROMPTS.md`).
- **Reporting** (`gmail/`): gatekeeper with token bucket, circuit breaker and
  DoS detector in front of the Gmail sender.
- **MCP server** (`mcp_server.py`): the inbound endpoint the opponent dials.

## 2. Requirements

### Input — what arrives on the wire

- `negotiate`: peer greeting with signed flat terms (exactly the 14
  `TERMS_KEYS` of `protocol/reference_v3.py`), lock hashes
  (`scent_model_sha256`, `wire_shape_sha256`), `game_uid`, role and sub-game
  index. Any mismatch is a deterministic refusal (SPAR-N02..N10) with a diag diff.
- `receive_turn`: sealed turn — exactly these keys: `step`, `sender`, `commit`
  (lowercase hex over `SHA256(canonical_json(payload) + "|" + nonce)`), `hint`,
  `smell_grid` (`{"r,c": value}`), `timestamp` (non-empty ISO-8601), and
  nullable `barrier_placed`, `capture_claim`, `claim_response`, `win_claim`.
  Cell fields are `[row, col]`. The move itself is NOT in the turn.
- `submit_audit`: `{sender, records: [{payload, nonce, commit}], result_claim}`
  with `result_claim` in {capture, survival, timeout, technical_loss}.

### Output — what we must produce

- Sealed turns of the identical shape (nonce withheld until audit; re-sends are
  byte-identical — equivocation is a refusal).
- Our own scent frame per turn, byte-exact under the locked model.
- An audit revealing every played step; verification of theirs must rehash all
  commits and bind each received commitment to its reveal.
- Per-series artifacts (config x6, log x6, declaration, result) via
  `scripts/ref3_artifacts.py`, and a result email through the gatekeeper.

### Behavioural constraints

- Movement never reads hints (`rl/local_obs_adapter.py` builds the tensor from
  position/barriers/scent/belief/scalars only).
- The serving guard (`rl/counted_policy.py`) must refuse to load a champion
  whose manifest `obs_mode` contradicts the live `COPTHIEF_*` environment.
- No LLM call during gameplay; the protocol-understanding agent runs pre-game
  only and never receives secrets, nonces or signing authority.
- The league/counted report address is never stored; friendly reports default
  to our own inbox (`gmail/gatekeeper.py::RECIPIENT`).
- Outbound MCP calls: 10 s per-call cap, at-least-once retry.

## 3. Constraints

- Python >= 3.12 (3.13 pinned), uv-managed; no network or LLM in unit tests.
- Byte-compatibility with the unmodified league kit (fixtures pinned against
  its `vectors/`); the kit is never edited.
- `config/game.json` is the single source of terms — wire terms, `config_sha256`
  and physics derive from it (drift-guard tested).

## 4. Success indicators

| Indicator | Target | Actual |
|---|---|---|
| Mutual audit verdicts, live series | 100% Verified OK | 12/12 (friendly + counted vs imreeyal) |
| Counted result | win | 90–30 vs imreeyal (cop captured sg2/4/6) |
| Test suite | green, no skips of live paths | ~1,478 tests pass |
| Branch coverage (CI gate) | >= 80% | passing |
| Kit conformance | all vectors | 125 checks / 15 fixtures PASS |

## 5. Test scenarios

- `tests/test_pursuit_search.py` — oracle property, capture short-circuits,
  enclosure, fallback discipline.
- `tests/test_scent_chebyshev.py` — byte-pinned against kit `vectors/pheromone.json`.
- `tests/test_config_single_source.py` — terms/sha/uid pins; no league address
  in runtime config.
- `tests/reference_v3/` + `test_codex_reference_v3_interop*.py` — wire shape,
  commit-reveal, refusal codes, real-process interop.
- `tests/test_serving_episode_reset.py` — policy reset between sub-games.
- Obs-mode guard: `test_obs_mode_guard` refuses env/manifest mismatch.
- End-to-end: `python scripts/live_match_ref3.py --self-test` against the kit's
  sparring peer (both roles) must settle with audits Verified OK.
