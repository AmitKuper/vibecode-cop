"""Render the three PNGs (trajectory, scent heatmap, search territory)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from arena_search_eval import N

from cop_worker.rl.pursuit_search import _dist_map


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
