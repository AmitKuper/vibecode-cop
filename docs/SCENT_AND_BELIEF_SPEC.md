# Scent and Belief Specification

## Scent Model

Both agents emit scent independently. The scent field uses a 5x5 Manhattan
kernel centered on the emitting agent's cell.

### Parameters

- Kernel size: 5x5 cells
- Distance metric: Manhattan (L1)
- Decay rate: DECAY = 0.9
- Emission center value: SCENT_CENTER (defined in agent/scent.py)

### Update Formula

```
scent[r][c](t+1) = DECAY * scent[r][c](t) + emission[r][c]
```

Where `emission[r][c]` is non-zero within the 5x5 kernel, falling off with
Manhattan distance from the agent's position.

### Observation Symmetry

- `cop_scent`: tracks accumulated cop presence
- `thief_scent`: tracks accumulated thief presence
- `cop_observation_scent()`: returns `thief_scent` (cop sees thief's scent)
- `thief_observation_scent()`: returns `cop_scent` (thief sees cop's scent)

Neither agent observes the opponent's true position — only the decaying scent.

## Bayesian Belief Model

Each agent maintains a belief distribution `belief[r][c]` over the opponent's
possible positions on the NxN grid.

### Initialization

Uniform over all non-barrier cells:
```
belief[r][c] = 1 / num_free_cells  for all free cells
belief[r][c] = 0                   for barrier cells
```

### Predict Step (Transition Prior)

Spread belief through legal transitions (N/S/E/W/STAY, no barrier crossings):
```
belief_predicted[r][c] = sum over neighbors n of (belief[n] / |legal_moves(n)|)
```

### Observe Step (Scent Likelihood)

Weight predicted belief by scent field:
```
belief_new[r][c] ∝ belief_predicted[r][c] × (scent[r][c] + 0.01)
```

The `+0.01` floor prevents zero-probability cells from becoming permanently
unreachable (Laplace smoothing).

### Normalization

After each update:
```
Z = sum(belief_new)
belief_new[r][c] = belief_new[r][c] / Z
```

### Usage

The belief heatmap is provided as an input channel to the recurrent A2C policy and
displayed in the live GUI belief overlay.
