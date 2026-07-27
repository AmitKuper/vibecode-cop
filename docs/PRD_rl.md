# PRD — RL Subsystem

> **Document type:** Component Product Requirements Document
> **Scope:** `agent/rl/` directory — training cop and thief RL policies for live-game strategy
> **Status:** v1.0

---

## 1. Purpose

The `agent/rl/` package provides reinforcement learning training and inference for the Cop & Thief game. It trains neural network policies for both roles using PPO and DQN algorithms, then exposes a lightweight inference wrapper (`RLPolicy`) that `GameOrchestrator` can use as a drop-in strategy.

The RL subsystem does not communicate over MCP, does not run live games, and does not depend on any external service. It is a standalone training and inference library.

---

## 2. Goals

1. Train cop and thief policies to a measurable win-rate improvement over heuristic baselines.
2. Produce serialised `.pt` checkpoints consumable by `RLPolicy` at inference time.
3. Enforce game-rules-compliant observations: thief sees only the last-revealed cop position, never the live board position.
4. Support self-play and league-play training modes.
5. Enable `GameOrchestrator` to use RL-trained strategy with zero changes to MCP protocol code.

---

## 3. Non-Goals

- The RL subsystem does not define game rules — it uses `Board` and `RulesEngine` from `agent/`.
- The RL subsystem does not talk to the MCP server/client stack.
- The RL subsystem does not train models in production; training happens offline before a game session.
- The RL subsystem does not guarantee trained models outperform heuristics on every game config — it provides the infrastructure; quality depends on training budget.

---

## 4. Key Components

### 4.1 `CopThiefEnv` (`agent/rl/environment.py`)

Gym-compatible simultaneous-action environment. Both agents act on the same step, mirroring the live commit-reveal protocol.

**Interface:**

```python
env = CopThiefEnv(config=RLGameConfig())
cop_obs, thief_obs = env.reset()
cop_obs, thief_obs, cop_reward, thief_reward, done, info = env.step(cop_action, thief_action)
```

**Action spaces:**

| Role | Space | Size |
|---|---|---|
| Thief | `["NORTH","SOUTH","EAST","WEST","STAY"]` | 5 |
| Cop (no barriers) | Same 5 moves | 5 |
| Cop (barriers enabled) | 5 moves + `["PLACE_N","PLACE_S","PLACE_E","PLACE_W"]` | 9 |

Illegal moves are silently replaced with `STAY`, matching live `GameRunner` behaviour.

**Reward modes:**

- Sparse: `+1` / `-1` on terminal, `-step_penalty` / `+step_penalty` each ongoing step.
- Shaped (optional): potential-based distance shaping — cop rewarded for reducing Manhattan distance to thief.

### 4.2 `RLGameConfig` (`agent/rl/config.py`)

Dataclass of training hyperparameters:

| Field | Default | Description |
|---|---|---|
| `grid_size` | 7 | Board dimension |
| `max_steps` | 35 | Max turns per game |
| `cop_start` | `[0, 0]` | Default cop start |
| `thief_start` | `[6, 6]` | Default thief start |
| `random_starts` | `False` | Randomise starts each episode |
| `cop_barrier_quota` | 0 | Barriers cop can place (0 = disabled) |
| `barriers` | `[]` | Fixed board barriers |
| `use_shaped_rewards` | `False` | Enable distance shaping |
| `shaped_reward_scale` | 0.1 | Shaping coefficient |
| `cop_capture_reward` | 1.0 | Terminal reward magnitude |
| `thief_survival_reward` | 1.0 | Terminal reward magnitude |
| `step_penalty` | 0.01 | Per-step ongoing signal |

### 4.3 Observation Builders (`agent/rl/observation.py`)

Asymmetric observations for each role. All observations are nested Python lists of shape `(channels, grid_size, grid_size)`.

**Cop observation (4 or 5 channels):**

| Channel | Content |
|---|---|
| 0 | Cop position (1-hot) |
| 1 | Barriers (1 = blocked) |
| 2 | Scent field (float 0.0–0.9, Chebyshev decay centred on thief) |
| 3 | Turns remaining (scalar broadcast, normalised 0–1) |
| 4 | Barriers remaining (only when `cop_barrier_quota > 0`) |

**Thief observation (4 channels — partial observability enforced):**

| Channel | Content |
|---|---|
| 0 | Thief position (1-hot) |
| 1 | Last-revealed cop position (1-hot) — NOT live board position |
| 2 | Barriers (1 = blocked) |
| 3 | Turns remaining (scalar broadcast, normalised 0–1) |

**Partial observability constraint:** `thief_observation` accepts `last_revealed_cop_pos` as an explicit argument. During live gameplay `GameOrchestrator` passes the cop position from the most recent completed reveal step. Passing `None` (offline self-play training) falls back to the live board position — this is acceptable for training but must not be used in production games.

### 4.4 Neural Networks (`agent/rl/networks.py`)

`PPONet`: shared-backbone actor-critic for convolutional policy. Input: `(C, H, W)` grid observation. Output: action logits + value estimate. Architecture: Conv2d layers → flatten → MLP → (actor head, critic head).

### 4.5 `PPOAgent` (`agent/rl/ppo.py`)

On-policy PPO trainer with Generalised Advantage Estimation (GAE).

Key hyperparameters:

| Parameter | Default | Description |
|---|---|---|
| `rollout_size` | 256 | Steps collected before each update |
| `n_epochs` | 4 | PPO update epochs per rollout |
| `clip_eps` | 0.2 | Surrogate clipping range |
| `gae_lambda` | 0.95 | GAE smoothing (1.0 = MC, 0.0 = TD) |
| `entropy_coef` | 0.01 | Entropy bonus for exploration |
| `lr` | 3e-4 | Adam learning rate |

Device: CPU by default. GPU beneficial only with vectorised environments.

### 4.6 `DQNAgent` (`agent/rl/dqn.py`)

Off-policy DQN with experience replay and target network.

Key hyperparameters:

| Parameter | Default | Description |
|---|---|---|
| `buffer_size` | 10000 | Replay buffer capacity |
| `batch_size` | 64 | Training batch |
| `target_update_freq` | 500 | Steps between target network syncs |
| `epsilon_start` | 1.0 | Initial exploration rate |
| `epsilon_end` | 0.05 | Final exploration rate |
| `epsilon_decay` | 0.995 | Per-episode decay multiplier |

### 4.7 `ReplayBuffer` (`agent/rl/replay_buffer.py`)

Fixed-capacity circular buffer of `(obs, action, reward, next_obs, done)` tuples. Used by `DQNAgent`.

### 4.8 Training Script (`agent/rl/train.py`)

Entry point for offline training. Supports:

- Self-play: both cop and thief policies trained simultaneously in the same environment.
- League training: one role uses a frozen checkpoint while the other trains.
- Saves best checkpoint by win rate to `models/<role>_ppo_best.pt` and `models/<role>_dqn_best.pt`.

Checkpoint naming convention:

| Filename | Description |
|---|---|
| `cop_ppo_best.pt` | Best cop PPO checkpoint by self-play win rate |
| `cop_ppo_league_best.pt` | Best cop PPO checkpoint trained against frozen thief |
| `thief_ppo_best.pt` | Best thief PPO checkpoint |
| `thief_ppo_league_best.pt` | Best thief PPO checkpoint trained against frozen cop |

### 4.9 Evaluation (`agent/rl/evaluate.py`)

Runs N evaluation episodes between two policies (or policy vs. heuristic) and returns win rates. Used after training to compare checkpoint quality before promotion.

### 4.10 `RLPolicy` (`agent/rl/policy.py`)

Inference-only wrapper. Loads a `.pt` checkpoint, exposes:

```python
policy = RLPolicy._load_checkpoint(path, role="cop", max_steps=35)
move: str = policy.select_move_from_dict(board_state_dict)
```

`select_move_from_dict` converts a `board_state` dict (same schema as `agent/memory/<id>/game_state.json`) into an observation tensor, runs the policy network, and returns a move string (`"NORTH"`, `"SOUTH"`, `"EAST"`, `"WEST"`, or `"STAY"`).

---

## 5. Training Modes

### 5.1 Self-Play

Both cop and thief policies train simultaneously. Each step both policies act; rewards and gradient updates are independent.

```bash
python -m agent.rl.train --mode self_play --episodes 10000 --role both
```

### 5.2 League Training Against Frozen Opponent

Freeze one role's latest best checkpoint and train the other. Rotates periodically to prevent overfitting to a single opponent policy.

```bash
python -m agent.rl.train --mode league --train_role cop --freeze_checkpoint models/thief_ppo_best.pt
```

---

## 6. Integration with GameOrchestrator

`GameOrchestrator._select_move_heuristic` queries `models/` for available checkpoints in preference order:

**Cop preference order:**
1. `cop_ppo_league_best.pt`
2. `cop_ppo_best.pt`
3. `cop_ppo_frozen_v2_best.pt`
4. `cop_ppo.pt`

**Thief preference order:**
1. `thief_ppo_league_best.pt`
2. `thief_ppo_frozen_v2_best.pt`
3. `thief_ppo_best.pt`
4. `thief_ppo.pt`

If no checkpoint is found, the orchestrator falls back to the role-specific heuristic strategy (`cop/strategy/` or `thief/strategy/`). If the heuristic also fails, `STAY` is returned.

The `strategy_tool` in `agent/tools/strategy_tool.py` wraps this selection so crewAI agents can invoke it as an MCP tool call within a crew's task.

---

## 7. Constraints

| Constraint | Enforcement |
|---|---|
| Thief partial observability | `thief_observation` uses `last_revealed_cop_pos`, never live board position in production |
| Illegal move handling | `CopThiefEnv.step` silently replaces illegal moves with `STAY` |
| Checkpoint format | PyTorch `.pt` state dict; architecture metadata stored alongside weights |
| No MCP dependency | `agent/rl/` imports only `agent/board.py`, `agent/rules_engine.py`, and standard library |
| CPU training default | Device selection defaults to CPU; GPU path requires explicit opt-in |

---

## 8. Acceptance Criteria

1. `CopThiefEnv.reset()` returns two observations of shape `(4, 7, 7)` (thief) and `(4, 7, 7)` or `(5, 7, 7)` (cop).
2. `CopThiefEnv.step()` reaches `done=True` within `max_steps` turns.
3. `PPOAgent` trains for 1000 episodes without NaN loss.
4. `DQNAgent` trains for 1000 episodes without NaN loss.
5. `RLPolicy._load_checkpoint` loads a valid `.pt` file and returns a move string for any valid board state dict.
6. Thief observation channel 1 reflects `last_revealed_cop_pos` when provided, not live cop position.
7. `GameOrchestrator` uses RL policy when checkpoint exists and falls back to heuristic when it does not.
8. League training produces a checkpoint with higher cop win rate than self-play baseline (evaluated over 500 episodes).
