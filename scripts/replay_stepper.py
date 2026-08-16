"""Interactive replay stepper over a reference-v3 wire log (book ch.7.4).

    python scripts/replay_stepper.py results/log_<game>_gNN.json

Keys: n = forward, p = backward, j <k> = jump to timeline index k, q = quit.
Each position shows the sealed payload, the stored commitment, the recomputed
SHA-256, and the per-step verdict; the footer always carries the whole-log
verdict (one TAMPERED step poisons the match). The verification core is shared
with the web /replay page — one implementation, two frontends.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cop_worker.replay.ref3_steps import verify_file  # noqa: E402


def _show(steps, i: int, overall: str) -> None:
    s = steps[i]
    p = s.payload
    print(f"\n--- timeline {i + 1}/{len(steps)}  ({s.side}, protocol step {s.step}) ---")
    if p.get("type") == "step_zero" or s.step == 0:
        print(
            f"  step-0 record: group={p.get('group_id')} commit={p.get('github_commit', '')[:12]}"
        )
    else:
        print(f"  move={p.get('move')} position={p.get('position')} intent={p.get('intent')}")
    print(f"  nonce      : {s.nonce}")
    print(f"  stored     : {s.stored_commit}")
    print(f"  recomputed : {s.recomputed_commit}")
    print(f"  step verdict: {s.verdict}    |    WHOLE LOG: {overall}")


def interactive(path: str) -> int:
    overall, steps = verify_file(path)
    if not steps:
        print("no sealed records in this log")
        return 1
    i = 0
    _show(steps, i, overall)
    while True:
        try:
            cmd = input("[n]ext [p]rev [j <k>]ump [q]uit > ").strip().lower()
        except EOFError:
            break
        if cmd == "q":
            break
        if cmd == "n" and i < len(steps) - 1:
            i += 1
        elif cmd == "p" and i > 0:
            i -= 1
        elif cmd.startswith("j"):
            try:
                i = min(max(int(cmd.split()[1]) - 1, 0), len(steps) - 1)
            except (IndexError, ValueError):
                print("usage: j <timeline-number>")
                continue
        _show(steps, i, overall)
    print(f"\nfinal verdict: {overall}")
    return 0 if overall == "Verified OK" else 1


if __name__ == "__main__":
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
        print(__doc__)
        sys.exit(2)
    sys.exit(interactive(sys.argv[1]))
