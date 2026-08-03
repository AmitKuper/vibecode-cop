"""Legal action spaces and masking for cop and thief."""

from __future__ import annotations

import numpy as np

COP_ACTIONS = ["N", "S", "E", "W", "STAY", "PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"]
THIEF_ACTIONS = ["N", "S", "E", "W", "STAY"]

MOVE_DELTAS = {"N": (-1, 0), "S": (1, 0), "E": (0, 1), "W": (0, -1), "STAY": (0, 0)}
PLACE_DIRS = {"PLACE_N": (-1, 0), "PLACE_S": (1, 0), "PLACE_E": (0, 1), "PLACE_W": (0, -1)}


def compute_legal_mask_cop(
    position: tuple[int, int],
    barriers: list[tuple[int, int]],
    barriers_remaining: int,
    grid_size: int,
) -> np.ndarray:
    """Returns bool array of shape (9,) for COP_ACTIONS."""
    mask = np.zeros(len(COP_ACTIONS), dtype=bool)
    barrier_set = set(map(tuple, barriers))
    r, c = position
    for i, action in enumerate(COP_ACTIONS):
        if action in MOVE_DELTAS:
            dr, dc = MOVE_DELTAS[action]
            nr, nc = r + dr, c + dc
            if 0 <= nr < grid_size and 0 <= nc < grid_size and (nr, nc) not in barrier_set:
                mask[i] = True
        elif action in PLACE_DIRS:
            if barriers_remaining <= 0:
                continue
            dr, dc = PLACE_DIRS[action]
            br, bc = r + dr, c + dc
            if 0 <= br < grid_size and 0 <= bc < grid_size and (br, bc) not in barrier_set:
                mask[i] = True
    return mask


def compute_legal_mask_thief(
    position: tuple[int, int],
    barriers: list[tuple[int, int]],
    grid_size: int,
) -> np.ndarray:
    """Returns bool array of shape (5,) for THIEF_ACTIONS."""
    mask = np.zeros(len(THIEF_ACTIONS), dtype=bool)
    barrier_set = set(map(tuple, barriers))
    r, c = position
    for i, action in enumerate(THIEF_ACTIONS):
        dr, dc = MOVE_DELTAS[action]
        nr, nc = r + dr, c + dc
        if 0 <= nr < grid_size and 0 <= nc < grid_size and (nr, nc) not in barrier_set:
            mask[i] = True
    return mask


def mask_logits(logits: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Set illegal actions to -inf before softmax."""
    masked = logits.copy().astype(float)
    masked[~mask] = -1e9
    return masked


def sample_action(
    logits: np.ndarray,
    mask: np.ndarray,
    mode: str = "argmax",
    temperature: float = 1.0,
) -> int:
    """Sample action index respecting legal mask."""
    masked_logits = mask_logits(logits, mask)
    if mode == "argmax":
        return int(np.argmax(masked_logits))
    # Softmax sampling
    shifted = masked_logits - masked_logits.max()
    exp = np.exp(shifted / max(temperature, 1e-6))
    exp[~mask] = 0.0
    total = exp.sum()
    if total < 1e-10:
        # Fallback: uniform over legal actions
        legal = np.where(mask)[0]
        return int(np.random.choice(legal))
    probs = exp / total
    return int(np.random.choice(len(probs), p=probs))
