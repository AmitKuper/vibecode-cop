# Extension Points — vibecode-cop

Where to plug in new behaviour without touching the counted match path. Every
seam below is grounded in the actual dispatch/loader site, not an aspiration.
Production entry point for all of them: `scripts/live_match_ref3.py` (DESIGN AD-1).

## New scent models

Register the model name and its locked doc hash in
`cop_worker/protocol/reference_v3/constants.py::SCENT_LOCKS`;
`cop_worker/protocol/reference_v3/negotiation.py` refuses any name not in that
dict and puts the lock hash on the wire at Step-0. Emission dispatch lives in
`RLMover.__init__` (`scripts/live_match_ref3.py`, `scent_model ==
"subtractive_chebyshev_v1"` branch): the chebyshev law is served by
`cop_worker/scent_chebyshev.py` (`ChebyshevTrail`), the book law by the
`Board`/`RulesEngine` engine (`cop_worker/scent.py`). A new model needs a lock
entry, an emission class, a dispatch branch, and — because the runner exports
`COPTHIEF_SCENT_MODEL` — an `obs_mode` shorthand in `cop_worker/rl/obs_mode.py`
so the serving guard (AD-8) can match trained checkpoints against it.

## New movement policies

Selected by `--move-policy {rl,hybrid_search,hybrid_search_belief}` (arg parsing
in `scripts/live_match_ref3.py`; profile default read from
`[protocol] move_policy` in the opponent's `runtime.toml`). Dispatch is again
`RLMover.__init__`: the base RL policy is always loaded via
`cop_worker/rl/counted_policy.py::load_counted_policy` (MANIFEST-pinned,
obs-mode guarded); `hybrid_search*` wraps it with
`cop_worker/rl/search_policy.py::wrap_with_search` (minimax over the chebyshev
oracle, RL fallback for blind frames); anything else raises `ValueError`. A new
policy is a new wrapper in the same shape plus a branch in that `if` — and, if
it needs a new checkpoint, an entry in `models/MANIFEST.json` with a correct
`obs_mode` block, or `counted_policy` will refuse the load.

## New opponents

Create `config/opponents/<group>/{game.json, runtime.toml}` and select it with
`--config <group>` (existing: `anrbj666`, `imreeyal`, `uoh-sqak`). The profile
carries the pairing-specific keys — `[protocol] scent_model` / `move_policy`
and the opponent endpoint URLs — on top of the base `config/`. The runner
auto-creates a missing profile from the base copy after a match but **never
overwrites existing profile files** (clobber guard in
`scripts/live_match_ref3.py`, live finding 2026-08-10). CLI flags override
profile values; the base `config/game.json` SHA must still match the peer's.

## New hint / language backends

`cop_worker/language/llm_hint.py` holds the provider dispatch: `provider ==
"ollama"` calls `cop_worker/language/llm_hint_backends.py::_call_ollama`
(direct httpx, `keep_alive` pinned); any other provider goes through a supplied
LLM object via `_call_crewai_llm`. The provider and model come from the
`[llm]` table of `runtime.toml` (`from_config`). Templates
(`cop_worker/language/hints.py`, policy in `hint_policy.py` /
`deception_policy.py`) are the unconditional fallback on error or timeout, so a
new backend only needs to return text-or-None inside the timeout — nothing
downstream changes.

## New report recipients

Friendly default is hardcoded to our own inbox:
`cop_worker/gmail/gatekeeper.py::RECIPIENT = "agentsorch@gmail.com"`. The
runner resolves the actual recipient as `--report-to` →
`[report] recipient` in `runtime.toml` → own inbox
(`scripts/live_match_ref3.py`). A counted run passes the league address **by
hand** via `--report-to`; it must never be stored —
`tests/test_config_single_source.py::test_runtime_toml_has_no_league_address`
fails the build if it appears in config (DESIGN AD-7). So a new recipient is a
profile `[report] recipient` (friendly) or a CLI argument (counted), never a
code or config constant.

## New protocol dialects

`league_manager/protocol/base.py::ProtocolAdapter` is the ABC: a dialect
declares `candidate_tool_names()` and implements `normalise_negotiate/turn/
audit/control` + `serialise_response` (wire translation only, no game logic).
`league_manager/protocol/detection.py::detect_protocol` runs the 5-stage
pipeline (discover tools → match candidate → version → handshake → lock) over
`adapter_classes`, defaulting to `[ReferenceV3Adapter]`
(`league_manager/protocol/reference_v3_adapter.py`). A new dialect subclasses
the ABC and is added to that candidate list; its wire constants belong beside
`cop_worker/protocol/reference_v3/constants.py` (dialect id, tool map, wire
lock). The pre-game LLM protocol-understanding agent
(`cop_worker/protocol/protocol_agent.py`) maps unknown-but-compatible
interfaces onto a profile before play; it is never used in-game.
