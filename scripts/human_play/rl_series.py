"""Series driver for the human-vs-rl CLI.

The argparse entry point (``main``) stays in the ``scripts/human_vs_rl.py``
facade: its ``epilog=__doc__`` must render that file's original usage docstring.
"""

from __future__ import annotations

import sys

from cop_worker.domain.config_validator import GameConfig
from cop_worker.rl.recurrent_policy import load_recurrent_policy
from cop_worker.rules_outcomes import GameOutcome
from human_play.keys import REPO, _clear
from human_play.rl_gamelet import _run_gamelet

# ── Series ────────────────────────────────────────────────────────────────────


def _run_series(human_role: str, n_gamelets: int, reveal: bool, numeric: bool) -> None:
    agent_role = "thief" if human_role == "cop" else "cop"

    print(f"\n  Loading RL champion for {agent_role} (from models/MANIFEST.json)...")
    manifest = REPO / "models" / "MANIFEST.json"
    if not manifest.exists():
        print(f"  ERROR: {manifest} not found. Run from the cop or thief repo root.")
        sys.exit(1)

    policy = load_recurrent_policy(manifest, agent_role)
    config = GameConfig()  # canonical Appendix-F config (6-gamelet series)

    print(f"  Policy loaded: {agent_role} champion ({policy.inference_mode}) — pure RL, no LLM")
    print("\n  Rules:")
    print(f"    Grid: {config.grid_size}×{config.grid_size}")
    print(f"    Max turns per gamelet: {config.max_moves}")
    print(f"    Cop starts at {config.cop_start}, Thief at {config.thief_start}")
    print("    Cop wins by: capture or trapping the thief")
    print(f"    Thief wins by: surviving {config.survival_threshold} turns")
    print(f"    Cop barriers: {config.max_barriers} total per gamelet")
    print("    Scent: shows opponent's historical trail (NOT exact position)")
    print("    Board legend: C=Cop  T=Thief  █=Barrier  ░▒▓=scent trail")
    if reveal:
        print("    --reveal: both positions shown (training/debug mode)")
    print(f"\n  {n_gamelets} gamelets. You play as {human_role.upper()}.")
    input("\n  Press Enter to start...")

    total_cop = total_thief = 0
    cop_wins = thief_wins = 0

    for i in range(1, n_gamelets + 1):
        c, t, outcome = _run_gamelet(i, human_role, agent_role, policy, config, reveal, numeric)
        total_cop += c
        total_thief += t
        if outcome == GameOutcome.COP_WIN.value:
            cop_wins += 1
        elif outcome == GameOutcome.THIEF_WIN.value:
            thief_wins += 1

    _clear()
    print("═" * 60)
    print("  SERIES COMPLETE")
    print("═" * 60)
    print(f"  Gamelets won — Cop: {cop_wins}  Thief: {thief_wins}")
    print(f"  Total score  — Cop: {total_cop}  Thief: {total_thief}")
    print()
    if human_role == "cop":
        you, agent = cop_wins, thief_wins
    else:
        you, agent = thief_wins, cop_wins

    if you > agent:
        print("  You beat the champion! The strategy may have a weakness here.")
    elif agent > you:
        print("  Champion wins the series. Strategy appears strong.")
    else:
        print("  Tied series.")
    print("═" * 60)
