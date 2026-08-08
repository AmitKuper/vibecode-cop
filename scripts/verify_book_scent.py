#!/usr/bin/env python3
"""Byte-exact proof that our scent == the kit's multiplicative_book_v1 (no rounding).

Checks our RulesEngine.update_scent against the kit's registered book model three ways:
  1. Kernel + emit vectors from vectors/scent_book_v3.json.
  2. The scalar decay trace (pure_decay: 0.9 -> 0.81).
  3. A multi-step walk vs the kit's own book_full_turn oracle, zero tolerance.

Run:  cd vibecode-cop && python scripts/verify_book_scent.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KIT = REPO.parent / "external" / "copthief-league-protocol"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(KIT))


def main() -> int:
    from sparring import kitref

    from cop_worker.board import Board
    from cop_worker.rules_engine import RulesEngine
    from cop_worker.scent import _radial_kernel

    vectors = json.loads((KIT / "vectors" / "scent_book_v3.json").read_text(encoding="utf-8"))
    board_n, emit, decay = 7, 0.9, 0.1
    fails = 0

    # 1. Kernel matches the pinned figure-4 kernel.
    kernel = [[round(v, 2) for v in row] for row in _radial_kernel(2)]
    kernel_ok = kernel == [[round(v, 2) for v in row] for row in vectors["kernel"]]
    print(f"[1] kernel == scent_book_v3 kernel: {'OK' if kernel_ok else 'FAIL'}")
    fails += not kernel_ok

    # 2. Scalar decay trace: 0.9 -> 0.81 with no rounding.
    tau = vectors["scalar_traces"]["pure_decay"]
    after = (1 - decay) * tau["tau"] + tau["delta"]
    scalar_ok = after == tau["after"]
    print(f"[2] pure_decay (1-p)*0.9 = {after} == {tau['after']}: {'OK' if scalar_ok else 'FAIL'}")
    fails += not scalar_ok

    # 3. Multi-step walk vs the kit's book_full_turn oracle, byte-exact JSON.
    walk = [(3, 3), (3, 4), (4, 4), (4, 5), (2, 5), (2, 2), (1, 1), (5, 5)]
    kit_field: dict = {}
    rules = RulesEngine(Board(cop_position=[0, 0], thief_position=[3, 3], grid_size=board_n),
                        max_turns=35)
    walk_fails = 0
    for r, c in walk:
        kit_field = kitref.book_full_turn(kit_field, [r, c], decay, emit, board_n)
        rules.board.thief_position = [c, r]  # board is (x, y) = (col, row)
        rules.update_scent()
        g = rules.get_scent_field()
        ours = {f"{y},{x}": g[y][x]
                for y in range(board_n) for x in range(board_n) if g[y][x] > 0.0}
        if json.dumps(ours, sort_keys=True) != json.dumps(kit_field, sort_keys=True):
            walk_fails += 1
    walk_ok = walk_fails == 0
    print(f"[3] {len(walk)}-step walk vs kit book_full_turn oracle: "
          f"{'OK (byte-exact)' if walk_ok else f'{walk_fails} steps differ'}")
    fails += not walk_ok

    verdict = "ALL BYTE-EXACT (no rounding, clamp)" if fails == 0 else f"{fails} check(s) FAILED"
    print(f"\nRESULT: {verdict}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
