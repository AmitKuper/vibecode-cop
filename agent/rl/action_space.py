"""Legal action spaces and masking for cop and thief."""

from __future__ import annotations

import numpy as np

COP_ACTIONS = ["N", "S", "E", "W", "STAY", "PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"]
THIEF_ACTIONS = ["N", "S", "E", "W", "STAY"]

MOVE_DELTAS = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0), "STAY": (0, 0)}
PLACE_DIRS = {
    "PLACE_N": (0, -1),
    "PLACE_S": (0, 1),
    "PLACE_E": (1, 0),
    "PLACE_W": (-1, 0),
}


def compute_legal_mask_cop(
    position: tuple[int, int],
    barriers: list[tuple[int, int]],
    barriers_remaining: int,
    grid_size: int,
) -> np.ndarray:
    """Returns bool array of shape (9,) for COP_ACTIONS."""
    mask = np.zeros(len(COP_ACTIONS), dtype=bool)
    barrier_set = set(map(tuple, barriers))
    x, y = position
    for i, action in enumerate(COP_ACTIONS):
        if action in MOVE_DELTAS:
            dx, dy = MOVE_DELTAS[action]
            nx, ny = x + dx, y + dy
            if 0 <= nx < grid_size and 0 <= ny < grid_size and (nx, ny) not in barrier_set:
                mask[i] = True
        elif action in PLACE_DIRS:
            if barriers_remaining <= 0:
                continue
            dx, dy = PLACE_DIRS[action]
            bx, by = x + dx, y + dy
            if 0 <= bx < grid_size and 0 <= by < grid_size and (bx, by) not in barrier_set:
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
    x, y = position
    for i, action in enumerate(THIEF_ACTIONS):
        dx, dy = MOVE_DELTAS[action]
        nx, ny = x + dx, y + dy
        if 0 <= nx < grid_size and 0 <= ny < grid_size and (nx, ny) not in barrier_set:
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
