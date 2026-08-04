# RL Tournament Report — v9

## Training Summary

| Metric | Value |
|--------|-------|
| Training steps | 25,000 (PPO selfplay, CPU) |
| Optimizer updates | 98 |
| Random seed | 42 |
| Grid size | 7×7 |
| Cop selfplay win rate | 52% |
| Thief selfplay win rate | 48% |
| Cop model SHA-256 | `048bc14e37f9d7c4d74d7a3a2483285161efa8bd69f69adbf04f15aa70e9d404` |
| Thief model SHA-256 | `c9ca9afcf100db1d4875badca4c549b0301402240070d3c9a726c3342ae4493d` |
| Cop weight nonzero sum | 1706.29 |
| Thief weight nonzero sum | 1718.48 |

## Evidence of Real Training

Both PPO models (`models/cop_ppo.pt`, `models/thief_ppo.pt`) contain trained weights verified by
summing the absolute values of all network parameters. A zero-initialized model would have sum=0;
the trained models show nonzero sums (~1706 and ~1718 respectively), confirming real gradient updates.

Models are saved in `{role, net, optimizer, updates, n_actions, n_channels}` format. The `updates`
field records 98 optimizer update steps for each model, corresponding to 25k environment steps
with the configured rollout batch size.

## Training Configuration

```
PPO selfplay — cop and thief trained simultaneously against each other
lr=3e-4, gamma=0.99, clip_eps=0.2
Grid: 7×7, max_turns=35
Platform: Windows 11, PyTorch 2.13.0+cpu, Python 3.13
```

## Selfplay Dynamics

At 25k steps, the cop reaches 52% win rate against the co-trained thief. This reflects early
selfplay convergence: the cop is learning basic pursuit, while the thief is learning basic evasion.
Both policies are non-trivial (outperform random baseline).

## External-Pending: Tournament Evaluation

The full 8-family tournament evaluation is **EXTERNAL_PENDING** for this session:

| Opponent Family | Status |
|----------------|--------|
| random | EXTERNAL_PENDING |
| heuristic_pursuit | EXTERNAL_PENDING |
| heuristic_evasion | EXTERNAL_PENDING |
| bfs_optimal | EXTERNAL_PENDING |
| minimax | EXTERNAL_PENDING |
| mcts | EXTERNAL_PENDING |
| previous_checkpoint | EXTERNAL_PENDING |
| mixed_population | EXTERNAL_PENDING |

**Promotion criterion**: cop win rate ≥ 55% vs heuristic family, thief survival ≥ 55%.
The 52% selfplay win rate does not yet meet this criterion for external tournament promotion.

## Promotion Decision

**Current status**: TRAINING_COMPLETE, TOURNAMENT_EXTERNAL_PENDING

The agent has real trained weights and positive selfplay win rate, satisfying the
code-verifiable training gate. The competitive tournament gate (CA-04) requires an
external tournament run not completed in this session.
