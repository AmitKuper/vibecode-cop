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
