#!/usr/bin/env python3
"""Score named candidate artifacts at REAL production settings and rank them.

``eval_policy_quality.py`` runs the full 2x2 belief x scent ablation on whatever the
MANIFEST points at. This is the narrow companion: given a list of candidate ``.pt`` files
for one role, play each through the same ``suite()`` at ``scent=wire`` / ``belief=prod``
only -- the single cell that describes a counted match -- so candidates are comparable to
each other and to the incumbent on one number.

Usage:
    python scripts/eval_candidate.py --role thief \
        --candidates models/thief_antiloop_candidate.pt \
        --games 30 --out reports/thief_candidates.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.eval_policy_quality import suite  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=("cop", "thief"), required=True)
    ap.add_argument(
        "--candidates",
        default="",
        help="comma-separated .pt paths; the manifest champion is always included",
    )
    ap.add_argument("--games", type=int, default=30, help="games per opponent family")
    ap.add_argument("--seed", type=int, default=20260809)
    ap.add_argument(
        "--scent",
        choices=("wire", "train", "chebyshev"),
        default="wire",
        help=(
            "field the policy READS. 'wire' is multiplicative_book_v1 clamped, what our "
            "champions trained on and what a counted match feeds today. 'chebyshev' is "
            "subtractive_chebyshev_v1, which a peer may lock instead -- use it to price that "
            "concession BEFORE agreeing to it at Step-0."
        ),
    )
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    # None => manifest champion, so the incumbent is always the first row of the ranking.
    entries: list[Path | None] = [None]
    entries += [Path(p.strip()) for p in args.candidates.split(",") if p.strip()]

    rows = []
    for artifact in entries:
        label = artifact.name if artifact else "MANIFEST champion"
        res = suite(args.role, "prod", args.games, args.seed, args.scent, artifact)
        res["label"] = label
        rows.append(res)
        worst = min(res["per_family"].items(), key=lambda kv: kv[1]["win_rate"])
        print(
            f"[{args.role}] {label:<36} win={res['overall_win_rate']:.4f} "
            f"({res['games']} games)  worst={worst[0]}@{worst[1]['win_rate']:.2f}"
        )
        for fam, m in res["per_family"].items():
            print(f"      {fam:<28} win={m['win_rate']:.2f}  avg_turns={m['avg_turns']}")

    rows.sort(key=lambda r: r["overall_win_rate"], reverse=True)
    print(f"\n=== {args.role} ranking at scent={args.scent} / belief=prod ===")
    for i, r in enumerate(rows, 1):
        print(f"  {i}. {r['label']:<36} {r['overall_win_rate']:.4f}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "role": args.role,
                    "scent_mode": args.scent,
                    "belief_mode": "prod",
                    "games_per_family": args.games,
                    "results": rows,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
