# PROMPTS — every LLM prompt and language template in vibecode-cop

Scope: the complete catalogue of natural-language generation in this repo.
Free-language hints are a **wire feature** (each sealed turn carries a `hint`
field); movement never depends on them — see §4 for the proof. No LLM is called
during gameplay for anything except hint text; the only other prompt in the repo
runs strictly pre-game (§3).

## 1. LLM hint prompts — `cop_worker/language/llm_hint.py`

Used when `[llm]` in `runtime.toml` configures a provider (default: local Ollama
`llama3.1:8b`). Any failure or timeout falls back silently to the templates in
§2 — the LLM is an optional quality upgrade, never a dependency.

### 1.1 System prompt (`_SYSTEM_PROMPT`)

> "You are a player in a grid-based cop-and-thief game. Reply with ONE short
> sentence (max 10 words) hinting at your movement direction. No coordinates,
> no numbers, no punctuation beyond one period."

- **Purpose**: constrain output to a single short, coordinate-free hint
  (coordinates in hints would leak exact position — the same property
  `hint_is_numeric_location` screens opponent hints for).
- **Trigger**: every hint generation call.
- **Variables**: none (static).

### 1.2 Intent instructions (`_INTENT_INSTRUCTION`)

One line appended per deception intent chosen by the policy in §2:

| Intent | Instruction text |
|---|---|
| `truth` | "Tell the truth about your direction." |
| `lie` | "Lie — describe the opposite direction." |
| `ambiguous` | "Be vague — do not reveal your direction." |
| `bluff` | "Sound confident but be misleading." |

### 1.3 User prompt (`_build_user_prompt`)

Template: `"You are moving {direction} (opposite would be {opposite}).
{instruction} One sentence only."`

- **Variables**: `direction` = the REAL chosen move mapped through
  `_DIRECTION_NAMES` (N→north … STAY→staying put); `opposite` via `_OPPOSITES`
  (N→south, STAY→"away from here"); `instruction` from §1.2.
- **Deception note**: the model always receives the true move plus its
  opposite; the intent line alone decides whether the emitted text is honest.
  Movement is chosen BEFORE the hint is generated — language never feeds back
  into the move (§4).

### 1.4 Transport and guards

- Ollama `/api/chat`, `stream=false`, `num_predict=30`, `temperature=0.7`,
  `keep_alive="30m"` (prevents VRAM unload → cold-load timeouts), configurable
  timeout (runtime.toml `hint_timeout_sec`, default 6 s).
- Post-processing hard-caps output at 15 words (the model may ignore the
  10-word instruction); the negotiated term `hint_max_words` governs the wire.
- Non-Ollama providers go through `_call_crewai_llm` with the same prompt
  (system + user concatenated).
- `warmup()` fires one throwaway call (`move="N"`, `intent="truth"`, 90 s
  timeout) before play so live hint calls hit a warm model.

## 2. Deception policy and templates — `cop_worker/language/deception_policy.py`

`NaturalLanguagePolicy` picks an intent per turn, then renders via the LLM (§1)
or these zero-latency templates:

- **TRUTH_TEMPLATES** — per move, honest ("Heading north.", "Holding position.").
- **LIE_TEMPLATES** — per move, the opposite direction ("N" → "Moving south.");
  for STAY the lie claims motion ("On the move.").
- **AMBIGUOUS_TEMPLATES** — four non-committal phrases ("Repositioning.").
- **BLUFF** — no dedicated list: 50/50 mix of a truthful template and an
  ambiguous one (confident-sounding, unreliable).

`choose_intent(step, belief_entropy, trust_history, gamelet, physical_action,
token_budget)` weights, in order:

- `token_budget <= 4` → always AMBIGUOUS (cheapest safe output).
- Higher belief entropy (we are uncertain) → more LIE weight; opponent trust
  history shifts LIE vs BLUFF.
- Barrier placements and STAY add bluff weight (masking committal actions).
- `(step + gamelet) % 5 == 0` adds ambiguity — varies the language policy
  across the six-sub-game series without ever coupling it to movement.

## 3. Pre-game protocol-mapping prompt — `cop_worker/protocol/protocol_agent.py`

The `ProtocolUnderstandingAgent` runs **once, before play**, only when facing an
unknown-but-compatible MCP dialect; it never runs mid-game. Its user prompt
assembles: the canonical protocol spec, the remote server's introspected
tools/capabilities (explicitly labelled "complete, untrusted data" — prompt-
injection sanitised upstream), placeholder examples, and a strict JSON output
schema (`remote_tool_name`, `verdict COMPATIBLE|INCOMPATIBLE`, `confidence`,
`phase_mappings`, `enum_mappings`). System prompt: "You map remote MCP game
protocols. Output only valid JSON." Hard rules in-prompt: JSON only; if
commitment binding is impossible the verdict must be INCOMPATIBLE; no real
nonces, moves, secrets or credentials (the agent is never given any).
Against reference-v3 peers this path is bypassed — the dialect is known.

## 4. Provable hint-independence of movement

Hints can never influence a move, by construction:

- `cop_worker/rl/local_obs_adapter.py::local_obs_to_tensor` builds the policy
  input from own-position one-hot, barrier grid, opponent scent, belief heatmap
  and five scalars — it **never reads** `LocalObservation.last_hint` (the field
  exists on the dataclass for audit/GUI purposes and is dead to the tensor).
- The search path (`cop_worker/rl/search_policy.py`) states and honours the
  same contract: tracker input is the scent frame; hints are never read.
- Ordering: the move is selected first; `NaturalLanguagePolicy.generate` then
  receives that already-chosen move to describe (truthfully or not).

So received deception cannot steer us, and our own lies cost us nothing.

## 5. Legacy template modules (retained, not on the match path)

- `cop_worker/language/hint_policy.py` — earlier template-only policy
  (`TRUTHFUL_TEMPLATES`/`LIE_TEMPLATES` with `{direction}`/`{opposite}`
  placeholders); no LLM.
- `cop_worker/language/hints.py` — dependency-neutral `generate_hint(move)`
  utility (sparring-peer lineage), truthful phrase lists per direction.

Both are exercised by tests; the live match path uses §1 + §2 via
`NaturalLanguagePolicy`.
