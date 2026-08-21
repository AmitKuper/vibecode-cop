"""Sealability: how many FUTURE walls would cut the thief off from open space.

Found by the operator (2026-08-21, eight play-mode games): the exact-table
evader is provably optimal against walls that exist and structurally blind
to walls that do not exist yet. An adaptive wall-placer herds it into a
region whose escape-cut is 1-2 cells, then closes it. The counter-invariant
is this module: the MIN VERTEX CUT between the thief and the far open cells
is exactly the number of future walls a perfect pocketer needs — a thief
that keeps its cut wide cannot be pocketed inside the cop's tempo.

Vertex min-cut via node-split max-flow (Edmonds-Karp) on the 7x7 grid:
every free cell costs 1 to wall, the thief's and cop's own cells cannot be
walled (infinite), sink = free cells at distance >= FAR from the thief.
49 nodes; microseconds per call.
"""

from __future__ import annotations

from collections import deque

ORTHO = ((-1, 0), (1, 0), (0, -1), (0, 1))
FAR = 4  # cells at least this Manhattan distance away count as "open space"
INF = 10**6


def sealability(thief, cop, walls, n: int = 7) -> int:
    """Min walls to cut ``thief`` off from all open space (INF-capped at 9)."""
    walls = set(map(tuple, walls))
    thief, cop = tuple(thief), tuple(cop)
    free = [(x, y) for x in range(n) for y in range(n) if (x, y) not in walls]
    far = [c for c in free if abs(c[0] - thief[0]) + abs(c[1] - thief[1]) >= FAR]
    if not far:
        return 0  # already confined to a small region — maximally sealable
    # node-split: cell -> (in=2i, out=2i+1); wallable cells carry capacity 1
    idx = {c: i for i, c in enumerate(free)}
    size = 2 * len(free) + 1
    sink = size - 1
    cap: list[dict[int, int]] = [{} for _ in range(size)]

    def add(u: int, v: int, c: int) -> None:
        cap[u][v] = cap[u].get(v, 0) + c
        cap[v].setdefault(u, 0)

    for c, i in idx.items():
        add(2 * i, 2 * i + 1, INF if c in (thief, cop) else 1)
        if c in far:
            add(2 * i + 1, sink, INF)
        for dx, dy in ORTHO:
            q = (c[0] + dx, c[1] + dy)
            if q in idx:
                add(2 * i + 1, 2 * idx[q], INF)
    source = 2 * idx[thief]
    flow = 0
    while flow < 9:  # capped: anything >= 9 is "unsealable" for our purposes
        parent = {source: -1}
        queue = deque([source])
        while queue and sink not in parent:
            u = queue.popleft()
            for v, c in cap[u].items():
                if c > 0 and v not in parent:
                    parent[v] = u
                    queue.append(v)
        if sink not in parent:
            break
        v = sink
        while v != source:
            u = parent[v]
            cap[u][v] -= 1
            cap[v][u] += 1
            v = u
        flow += 1
    return flow
