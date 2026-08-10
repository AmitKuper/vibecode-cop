"""Render real-engine match visuals: trajectory, chebyshev scent, search territory.

Plays a real game with the production physics (rule-46/47, ChebyshevTrail) between
the shipped hybrid-search policies, then renders three PNGs under assets/:
  1. match_trajectory.png     — both paths + barriers on the 7x7 board
  2. scent_heatmap.png        — the thief's transmitted chebyshev field mid-game
  3. search_territory.png     — the cop search engine's territory evaluation

Usage: python scripts/render_match_visuals.py [--seed 20260811] [--out assets]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from arena_search_eval import N, make_policy  # noqa: E402

from cop_worker.observation import BeliefState, LocalObservation  # noqa: E402
from cop_worker.rl.action_space import (  # noqa: E402
    COP_ACTIONS,
    MOVE_DELTAS,
    PLACE_DIRS,
    THIEF_ACTIONS,
    compute_legal_mask_cop,
    compute_legal_mask_thief,
)
from cop_worker.rl.pursuit_search import _dist_map  # noqa: E402
from cop_worker.scent_chebyshev import ChebyshevTrail  # noqa: E402


def _obs(own, remaining, barriers, scent_grid, step):
    return LocalObservation(
        own_position=tuple(own),
        own_barriers_remaining=remaining,
        known_barriers=[tuple(b) for b in barriers],
        opponent_scent=scent_grid,
        last_hint="",
        step=step,
        gamelet=1,
        grid_size=N,
    )


def play_and_record(seed: int):
    """Replay of arena_search_eval.play that records every state."""
    cop_policy = make_policy("search", "cop", 4)
    thief_policy = make_policy("search", "thief", 4)
    cop, thief = [0, 0], [3, 3]
    barriers: list[list[int]] = []
    remaining = 14
    cop_trail, thief_trail = ChebyshevTrail(N), ChebyshevTrail(N)
    cop_policy.reset()
    thief_policy.reset()
    cop_frame = [[0.0] * N for _ in range(N)]
    history = {"cop": [tuple(cop)], "thief": [tuple(thief)], "scent": [], "barriers": []}
    history["outcome"] = "survival"
    end_step = 35
    for step in range(1, 36):
        mask = compute_legal_mask_thief(tuple(thief), [tuple(b) for b in barriers], N)
        legal = [a for a, m in zip(THIEF_ACTIONS, mask) if m]
        if not any(a != "STAY" for a in legal):
            history["outcome"] = "capture"
            end_step = step
            break
        act = thief_policy.select_action(
            _obs(thief, 0, barriers, cop_frame, step), BeliefState.uniform(N, step=step), legal
        )
        dx, dy = MOVE_DELTAS[act]
        thief = [thief[0] + dx, thief[1] + dy]
        history["thief"].append(tuple(thief))
        if thief == cop:
            history["outcome"] = "capture"
            end_step = step
            break
        wire = thief_trail.full_turn((thief[1], thief[0]))
        thief_frame = [[wire.get(f"{r},{c}", 0.0) for c in range(N)] for r in range(N)]
        history["scent"].append([row[:] for row in thief_frame])
        mask = compute_legal_mask_cop(tuple(cop), [tuple(b) for b in barriers], remaining, N)
        legal = [a for a, m in zip(COP_ACTIONS, mask) if m] or ["STAY"]
        act = cop_policy.select_action(
            _obs(cop, remaining, barriers, thief_frame, step),
            BeliefState.uniform(N, step=step),
            legal,
        )
        if act in PLACE_DIRS:
            dx, dy = PLACE_DIRS[act]
            cell = [cop[0] + dx, cop[1] + dy]
            if 0 <= cell[0] < N and 0 <= cell[1] < N and cell not in barriers and remaining > 0:
                barriers.append(cell)
                remaining -= 1
                if cell == thief:
                    history["outcome"] = "capture"
                    end_step = step
                    break
        else:
            dx, dy = MOVE_DELTAS[act]
            cop = [cop[0] + dx, cop[1] + dy]
            if cop == thief:
                history["cop"].append(tuple(cop))
                history["outcome"] = "capture"
                end_step = step
                break
        history["cop"].append(tuple(cop))
        history["barriers"].append([tuple(b) for b in barriers])
        wire = cop_trail.full_turn((cop[1], cop[0]))
        cop_frame = [[wire.get(f"{r},{c}", 0.0) for c in range(N)] for r in range(N)]
    history["end_step"] = end_step
    history["final_barriers"] = [tuple(b) for b in barriers]
    history["final"] = (tuple(cop), tuple(thief))
    return history


def render(history, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []

    # 1. trajectory
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.set_title(
        f"hybrid_search vs hybrid_search — {history['outcome']} at step {history['end_step']}"
    )
    for x in range(N + 1):
        ax.axhline(x - 0.5, color="#dddddd", lw=0.6)
        ax.axvline(x - 0.5, color="#dddddd", lw=0.6)
    for bx, by in history["final_barriers"]:
        ax.add_patch(plt.Rectangle((bx - 0.5, by - 0.5), 1, 1, color="#444444"))
    cx, cy = zip(*history["cop"])
    tx, ty = zip(*history["thief"])
    ax.plot(cx, cy, "-o", color="#1f77b4", label="cop", ms=4)
    ax.plot(tx, ty, "-s", color="#d62728", label="thief", ms=4)
    ax.plot(cx[-1], cy[-1], "o", color="#1f77b4", ms=12)
    ax.plot(tx[-1], ty[-1], "s", color="#d62728", ms=12)
    ax.set_xlim(-0.5, N - 0.5)
    ax.set_ylim(N - 0.5, -0.5)
    ax.set_aspect("equal")
    ax.legend(loc="upper right")
    p = out / "match_trajectory.png"
    fig.savefig(p, dpi=120, bbox_inches="tight")
    plt.close(fig)
    written.append(p)

    # 2. mid-game scent heatmap (thief's transmitted chebyshev field)
    mid = len(history["scent"]) // 2
    frame = history["scent"][mid]
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(frame, cmap="magma", vmin=0.0, vmax=0.9)
    ax.set_title(f"thief chebyshev scent field (wire snapshot, step {mid + 1})")
    fig.colorbar(im, ax=ax, label="intensity")
    p = out / "scent_heatmap.png"
    fig.savefig(p, dpi=120, bbox_inches="tight")
    plt.close(fig)
    written.append(p)

    # 3. search territory evaluation from the mid-game position
    cop_pos = history["cop"][min(mid, len(history["cop"]) - 1)]
    thief_pos = history["thief"][min(mid, len(history["thief"]) - 1)]
    barriers = (
        history["barriers"][min(mid, len(history["barriers"]) - 1)] if history["barriers"] else []
    )
    td = _dist_map(thief_pos, frozenset(barriers), N)
    cd = _dist_map(cop_pos, frozenset(barriers), N)
    grid = [[0] * N for _ in range(N)]
    for cell, d in td.items():
        if d < cd.get(cell, 10_000):
            grid[cell[1]][cell[0]] = 1
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(grid, cmap="RdBu", vmin=0, vmax=1)
    ax.plot(cop_pos[0], cop_pos[1], "o", color="#1f77b4", ms=14)
    ax.plot(thief_pos[0], thief_pos[1], "s", color="#d62728", ms=14)
    for bx, by in barriers:
        ax.add_patch(plt.Rectangle((bx - 0.5, by - 0.5), 1, 1, color="#444444"))
    ax.set_title("search engine territory eval (blue=thief-first cells)")
    p = out / "search_territory.png"
    fig.savefig(p, dpi=120, bbox_inches="tight")
    plt.close(fig)
    written.append(p)
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260811)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "assets" / "screenshots")
    args = parser.parse_args()
    history = play_and_record(args.seed)
    for path in render(history, args.out):
        print(path)


if __name__ == "__main__":
    main()
