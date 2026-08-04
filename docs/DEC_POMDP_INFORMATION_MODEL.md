# Dec-POMDP Information Model

## Definition

This game is modelled as a **Decentralised Partially Observable Markov Decision Process
(Dec-POMDP)** with two agents (cop, thief), finite horizon T = 35 turns, and a 7×7 grid.

Formally: (S, {A_i}, T, R, {Ω_i}, O, h) where:
- **S** — joint state: (cop_pos, thief_pos, barriers, turn)
- **A_i** — per-agent actions: {N, S, E, W, STAY, BARRIER_*}
- **T** — deterministic transition given joint actions
- **R** — cop wins on capture; thief wins on surviving T turns
- **Ω_i** — local observation spaces (see below)
- **O** — observation function (identity on own position, scent proxy for opponent)
- **h** — finite horizon (35)

## Local Observation Space

Each agent observes at each turn:
```
own_position       : (row, col)  — exact, known
own_move_history   : list[str]   — full own trajectory
scent_field        : float[7][7] — diffused scent from thief movement
turn               : int         — current step number
```

## Partial Observability: Hidden Opponent Coordinate

Neither agent directly observes the opponent's position:
- **Cop** sees `scent_field` but NOT `thief_position`
- **Thief** sees `scent_field` but NOT `cop_position`

The hidden variable is the opponent's (row, col) — a 49-element discrete space.

## Scent as Proxy Signal

Scent diffuses from the thief's position each turn via a Gaussian kernel.
The cop observes the resulting field — a noisy, delayed indirect signal:
- High scent near a cell → thief was recently nearby
- Scent decays each turn, so recency is partially encoded in magnitude
- Barriers do not block scent diffusion (simplified model)

## Belief State

Each agent maintains an implicit **belief distribution** B(s) over the hidden
opponent position:
```
B_cop(thief_pos) ∝ P(scent_field | thief_pos) × P(thief_pos | prior)
```
The RL policy implicitly encodes this belief via the CNN over the scent field.
Explicit Bayesian belief tracking is an optional extension.

## Information Asymmetry

| Agent | Knows own pos | Knows opponent pos | Sees scent |
|-------|:---:|:---:|:---:|
| Cop   | ✓   | ✗   | ✓  |
| Thief | ✓   | ✗   | ✓  |

Both agents have symmetric structural partial observability.
The **commitment protocol** (Phase 10B) is necessary precisely because each agent
cannot verify the opponent's move before committing its own — preventing adaptive
cheating based on observing the opponent's pre-move intention.

## Production Observation Builder (Phase 2 v7)

`build_local_observation()` in `agent/peer_turn_helpers.py` is the **sole** entry
point for constructing strategy/RL observations in the production turn loop.
It replaces the legacy `build_observation()` which accidentally included both
`cop_position` and `thief_position` in `grid_state`.

### What each role sees

| Field | Cop | Thief |
|-------|:---:|:-----:|
| `own_position` (own true coords) | ✓ | ✓ |
| `known_barriers` (public) | ✓ | ✓ |
| `opponent_scent` (NxN float) | thief scent | cop scent |
| `belief_heatmap` (NxN float) | ✓ if BeliefEngine wired | ✓ if BeliefEngine wired |
| `belief_entropy` | ✓ if BeliefEngine wired | ✓ if BeliefEngine wired |
| `last_hint` | ✓ | ✓ |
| `step`, `gamelet`, `grid_size` | ✓ | ✓ |
| `cop_position` (hidden!) | ✗ | ✗ |
| `thief_position` (hidden!) | ✗ | ✗ |
| `opponent_position` (hidden!) | ✗ | ✗ |

The RL adapter `local_obs_to_tensor()` in `agent/rl/local_obs_adapter.py` operates
on `LocalObservation` which by design has no opponent-coordinate field, making
hidden-coordinate leaks a type-level impossibility for the RL path.

## Why No Objective State Reaches the Actor

The full state S = (cop_pos, thief_pos, barriers, turn) is never transmitted to
either actor during gameplay. Each agent receives only its local observation Ω_i.
This is enforced at the protocol level:
- Commits are hashed — the move is hidden until both have committed
- Reveals are verified against the prior commit hash
- The coordinator (ProtocolCoordinator) enforces ordering; no state broadcast occurs
- `build_local_observation()` is role-filtered — hidden opponent coordinate is
  structurally excluded, not just omitted by convention

Any actor that could see the full S would break the Dec-POMDP structure and allow
trivially optimal policies — eliminating the game's strategic depth.
