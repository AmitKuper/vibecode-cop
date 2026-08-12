"""CLI: audit the deployed policies across families, scent modes, and belief modes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cop_worker.rl.research_evaluation import ScriptedResearchPolicy
from eval_reasonableness.audit import audit_game
from eval_reasonableness.metrics import summarise
from scripts.eval_policy_quality import DeployedPolicy


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20260809)
    ap.add_argument("--opponent", default="belief_pursuit_evasion")
    ap.add_argument(
        "--opponents",
        default=None,
        help="comma-separated families to average over (overrides --opponent)",
    )
    ap.add_argument(
        "--scent-mode",
        choices=("train", "wire", "both"),
        default="wire",
        help="'wire' = the clamped field production really carries (default)",
    )
    ap.add_argument(
        "--belief-modes", default="prod", help="comma-separated: prod (production), live"
    )
    ap.add_argument(
        "--cop-artifact", type=Path, default=None, help="candidate .pt instead of the manifest cop"
    )
    ap.add_argument("--thief-artifact", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    families = [f.strip() for f in args.opponents.split(",")] if args.opponents else [args.opponent]
    scent_modes = ("train", "wire") if args.scent_mode == "both" else (args.scent_mode,)
    belief_modes = [m.strip() for m in args.belief_modes.split(",")]

    report = {
        "opponents": families,
        "games_per_opponent": args.games,
        "scent_modes": list(scent_modes),
        "results": {},
    }
    for role in ("cop", "thief"):
        artifact = args.cop_artifact if role == "cop" else args.thief_artifact
        for scent_mode in scent_modes:
            for mode in belief_modes:
                ours = DeployedPolicy(role, mode, artifact)
                rows = []
                for family in families:
                    opp = ScriptedResearchPolicy("thief" if role == "cop" else "cop", family)
                    rows += [
                        audit_game(role, ours, opp, args.seed + i * 7919, (i % 6) + 1, scent_mode)
                        for i in range(args.games)
                    ]
                s = summarise(rows)
                key = f"{role}/belief={mode}/scent={scent_mode}"
                report["results"][key] = s
                tag = "  <-- REAL PRODUCTION" if (scent_mode, mode) == ("wire", "prod") else ""
                which = artifact.name if artifact else "manifest champion"
                print(f"\n[{key}] {which} vs {len(families)} families{tag}")
                for k, v in s.items():
                    print(f"    {k:<24} {v}")

    if args.out:
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")
