# Prompt Engineering Log

## LLM Role in Production

The LLM (Claude) is used for **free-language hints only** — not for movement
decisions. Movement is handled exclusively by the PPO policy or the heuristic
fallback (pursuit agent for cop).

## Hint Generation

Hints are generated via template-based policy in `agent/language/hint_policy.py`.
Two variants exist:

- **Truth hints**: disclose (partial) true state, e.g. "I am in the NW quadrant"
- **Lie hints**: strategic deception, e.g. "I am heading east" (when going west)

The hint policy selects truth or lie based on configurable deception rate
and current game state (score differential, turn number).

The LLM may be invoked to paraphrase a template hint into natural language,
adding variability that makes deception harder to detect.

## Protocol Mapping

During Step-0 (capability discovery), the LLM may propose a tool-name mapping
once. After Step-0 completes, the mapping is locked into `GameProtocolPort`
and all subsequent calls use deterministic tool names — no further LLM
involvement in protocol decisions.

## Token Budget

Token usage is tracked per gamelet and included in `ResultAgreement.token_totals`.
Both agents report token totals; the bilateral agreement ensures consistency.

## Deception Strategy

The thief benefits more from deceptive hints (evasion strategy). The cop
benefits from neutral/misleading hints to conceal pursuit direction.
Deception rate is a configurable hyperparameter (default: 0.3 for thief).

## Non-Usage Guarantee

The PPO policy receives `LocalObservation` which does NOT include:
- opponent's true position
- LLM-generated text
- any information not available via the scent field or belief distribution

This satisfies the Dec-POMDP hidden-information requirement (AC4).

## Phase 4 v7: DeceptionIntent Enum and NaturalLanguagePolicy

`agent/language/deception_policy.py` introduces:

### DeceptionIntent Enum
- `TRUTH` — hint accurately reflects actual move direction
- `AMBIGUOUS` — vague, non-directional hint ("Repositioning.")
- `LIE` — hint states opposite direction to actual move
- `BLUFF` — mix of truth and misdirection; context-dependent

### NaturalLanguagePolicy
- Language policy is **separate from movement control** (movement: RL/heuristic)
- `choose_intent(step, belief_entropy)` — selects intent dynamically:
  - High belief entropy → more likely to LIE (opponent is uncertain anyway)
  - Low belief entropy → TRUTH or BLUFF (keep opponent off-balance)
- `generate(move, intent)` — template-based, never includes numeric coordinates
- `bluff_probability` configurable (default 0.3)

### No Numeric-Location Protocol
All templates are direction-only (e.g. "Heading north."). The method
`hint_is_numeric_location()` detects forbidden patterns like `(row, col)` or
`position (3,4)`. Tests enforce this invariant.

### Opponent Hint Profiling
`record_opponent_hint(hint)` accumulates opponent hints for future behavioral
analysis. `opponent_hint_count()` tracks how many opponent hints have been seen.
