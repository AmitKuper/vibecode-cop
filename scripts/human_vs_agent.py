#!/usr/bin/env python3
"""Human vs Agent interactive CLI — play against the production cop or thief policy.

Run from the vibecode-cop or vibecode-thief directory:

    uv run python scripts/human_vs_agent.py --human-role thief
    uv run python scripts/human_vs_agent.py --human-role cop
    uv run python scripts/human_vs_agent.py --human-role thief --reveal

Flags:
  --human-role {cop,thief}   Which role you play (agent plays the other)
  --reveal                   Show both positions after each turn (full board)
  --numeric                  Show scent/belief as floats instead of ░▒▓ chars
  --gamelets N               Number of gamelets to play (default 3)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ── Cross-platform single-keypress capture ─────────────────────────────────────

if os.name == "nt":
    import msvcrt

    def _get_key() -> str:
        """Return a normalised key name (one blocking read, no Enter needed)."""
        ch = msvcrt.getch()
        if ch in (b"\xe0", b"\x00"):          # arrow / function-key prefix
            ch2 = msvcrt.getch()
            return {b"H": "UP", b"P": "DOWN", b"K": "LEFT", b"M": "RIGHT"}.get(ch2, "")
        if ch == b" ":
            return "SPACE"
        if ch == b"\r":
            return "ENTER"
        if ch == b"\x1b":
            return "ESC"
        try:
            return ch.decode("utf-8").upper()
        except UnicodeDecodeError:
            return ""
else:
    import tty
    import termios

    def _get_key() -> str:  # type: ignore[misc]
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    return {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}.get(ch3, "")
                return "ESC"
            if ch == " ":
                return "SPACE"
            if ch == "\r":
                return "ENTER"
            if ch == "\x1b":
                return "ESC"
            return ch.upper()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agent.belief_engine import BeliefEngine
from agent.domain.config_validator import GameConfig
from agent.domain.transition import apply_joint_action
from agent.domain.types import DomainState
from agent.observation import LocalObservation
from agent.rl.action_space import (
    COP_ACTIONS,
    THIEF_ACTIONS,
    compute_legal_mask_cop,
    compute_legal_mask_thief,
)
from agent.rl.recurrent_policy import load_recurrent_policy
from agent.rules_outcomes import GameOutcome


# ── Visual constants ──────────────────────────────────────────────────────────

_SCENT_RAMP = " ·░▒▓"   # 5 levels: empty → faint → dense


def _scent_ch(v: float) -> str:
    idx = min(int(v * len(_SCENT_RAMP)), len(_SCENT_RAMP) - 1)
    return _SCENT_RAMP[idx]


def _clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


# ── Board rendering ───────────────────────────────────────────────────────────

def _render_board(
    state: DomainState,
    human_role: str,
    reveal: bool,
    agent_belief: BeliefEngine,
    numeric: bool = False,
) -> str:
    """
    Render the 7×7 board from the human's perspective.

    Visibility rules:
      - You always see your own position.
      - Scent field shows opponent's historical trail (NOT live position).
      - Opponent exact position is hidden unless --reveal is set.
      - Barriers (█) are always visible to both sides.
    """
    g = state.grid_size
    barrier_set = {tuple(b) for b in state.barriers}
    cop_pos = tuple(state.cop_position)
    thief_pos = tuple(state.thief_position)

    # Scent the human sees: opponent's emission trail
    if human_role == "cop":
        scent = state.thief_scent
    else:
        scent = state.cop_scent

    if numeric:
        col_header = "    " + "  ".join(str(x) for x in range(g))
        sep = "    " + "─" * (g * 4 - 1)
    else:
        col_header = "   " + "  ".join(str(x) for x in range(g))
        sep = "   " + "─" * (g * 3 - 1)
    rows = [col_header, sep]

    for row in range(g):
        cells = [f"{row} │"]
        for col in range(g):
            pos = (col, row)
            if pos in barrier_set:
                ch = " █  " if numeric else " █ "
            elif pos == cop_pos and (human_role == "cop" or reveal):
                ch = " C  " if numeric else " C "
            elif pos == thief_pos and (human_role == "thief" or reveal):
                ch = " T  " if numeric else " T "
            elif reveal and pos == cop_pos:
                ch = " c  " if numeric else " c "
            elif reveal and pos == thief_pos:
                ch = " t  " if numeric else " t "
            else:
                sv = scent[row][col] if scent else 0.0
                if numeric:
                    ch = f"{sv:4.2f}" if sv > 0 else "   ."
                else:
                    ch = f" {_scent_ch(sv)} "
            cells.append(ch)
        rows.append("".join(cells))

    # Belief heatmap
    belief_grid = agent_belief.belief.prob
    rows.append("")
    if numeric:
        rows.append("   Agent's belief of YOUR position (probability):")
        rows.append("    " + "  ".join(str(x) for x in range(g)))
        for row in range(g):
            cells = [f"{row}   "]
            for col in range(g):
                cells.append(f"{belief_grid[row][col]:4.2f}")
            rows.append("".join(cells))
    else:
        rows.append("   Agent's belief of YOUR position (brighter = more likely):")
        rows.append("   " + "  ".join(str(x) for x in range(g)))
        for row in range(g):
            cells = ["   "]
            for col in range(g):
                v = belief_grid[row][col]
                cells.append(f" {_scent_ch(min(v * (g * g) / 2, 1.0))} ")
            rows.append("".join(cells))
    rows.append(
        f"   entropy={agent_belief.belief.entropy:.2f}  "
        f"confidence={agent_belief.belief.confidence:.2f}"
    )

    return "\n".join(rows)


# ── Legal move display ────────────────────────────────────────────────────────

def _legal_moves_for(role: str, state: DomainState) -> list[str]:
    if role == "cop":
        mask = compute_legal_mask_cop(
            tuple(state.cop_position), state.barriers,
            state.cop_barriers_remaining, state.grid_size,
        )
        return [a for a, ok in zip(COP_ACTIONS, mask) if ok]
    else:
        mask = compute_legal_mask_thief(
            tuple(state.thief_position), state.barriers, state.grid_size,
        )
        return [a for a, ok in zip(THIEF_ACTIONS, mask) if ok]


# ── Human input (keyboard) ────────────────────────────────────────────────────

# Maps raw key name → movement action
_KEY_TO_MOVE = {
    "UP": "N", "W": "N",
    "DOWN": "S", "S": "S",
    "LEFT": "W", "A": "W",
    "RIGHT": "E", "D": "E",
    "SPACE": "STAY",
}

# Maps raw key name → barrier-placement action (used in barrier mode)
_KEY_TO_PLACE = {
    "UP": "PLACE_N", "W": "PLACE_N",
    "DOWN": "PLACE_S", "S": "PLACE_S",
    "LEFT": "PLACE_W", "A": "PLACE_W",
    "RIGHT": "PLACE_E", "D": "PLACE_E",
}

_CONTROLS_THIEF = (
    "  ↑W  ↓S  ←A  →D  Space=STAY   Q=quit"
)
_CONTROLS_COP = (
    "  ↑W  ↓S  ←A  →D  Space=STAY   B=barrier mode   Q=quit"
)
_CONTROLS_COP_BARRIER = (
    "  [BARRIER MODE] ↑W↓S←A→D=place direction   Esc=cancel"
)


def _get_human_move(legal: list[str], role: str) -> str:
    """Blocking single-keypress move selection; returns a legal action string."""
    barrier_mode = False

    if role == "cop":
        print(_CONTROLS_COP)
    else:
        print(_CONTROLS_THIEF)
    print(f"  Legal: {' '.join(legal)}")
    print("  Your move: ", end="", flush=True)

    while True:
        key = _get_key()

        # Quit
        if key in ("Q", "ESC") and not barrier_mode:
            if key == "Q":
                print("\n  Quit.")
                sys.exit(0)

        # Enter barrier mode (cop only, when barriers remain)
        if key == "B" and role == "cop" and not barrier_mode:
            can_place = any(a.startswith("PLACE_") for a in legal)
            if can_place:
                barrier_mode = True
                print(f"\r{_CONTROLS_COP_BARRIER}", end="", flush=True)
                continue
            else:
                # No barriers left — flash message
                print(f"\r  No barriers remaining.      ", end="", flush=True)
                continue

        # Cancel barrier mode
        if barrier_mode and key == "ESC":
            barrier_mode = False
            print(f"\r{_CONTROLS_COP}                              ", end="", flush=True)
            continue

        # Resolve action
        if barrier_mode:
            action = _KEY_TO_PLACE.get(key, "")
        else:
            action = _KEY_TO_MOVE.get(key, "")

        if action and action in legal:
            label = f"[barrier] {action}" if barrier_mode else action
            print(f"\r  Your move: {label}          ")
            return action

        # Key not legal — silently loop (no error spam on keypress)


# ── Agent move ────────────────────────────────────────────────────────────────

def _get_agent_move(
    agent_role: str,
    state: DomainState,
    policy,
    belief: BeliefEngine,
    gamelet: int,
) -> str:
    if agent_role == "cop":
        mask = compute_legal_mask_cop(
            tuple(state.cop_position), state.barriers,
            state.cop_barriers_remaining, state.grid_size,
        )
        legal = [a for a, ok in zip(COP_ACTIONS, mask) if ok]
        scent = state.thief_scent
    else:
        mask = compute_legal_mask_thief(
            tuple(state.thief_position), state.barriers, state.grid_size,
        )
        legal = [a for a, ok in zip(THIEF_ACTIONS, mask) if ok]
        scent = state.cop_scent

    obs = LocalObservation(
        own_position=tuple(state.cop_position) if agent_role == "cop" else tuple(state.thief_position),
        own_barriers_remaining=state.cop_barriers_remaining if agent_role == "cop" else 0,
        known_barriers=list(state.barriers),
        opponent_scent=scent,
        last_hint="",
        step=state.turn,
        gamelet=gamelet,
        grid_size=state.grid_size,
    )
    return policy.select_action(obs, belief.belief, legal)


# ── Gamelet ───────────────────────────────────────────────────────────────────

def _run_gamelet(
    gamelet_num: int,
    human_role: str,
    agent_role: str,
    policy,
    config: GameConfig,
    reveal: bool,
    numeric: bool = False,
) -> tuple[int, int, str]:
    """Play one gamelet. Returns (cop_score, thief_score, outcome_label)."""
    g = config.grid_size
    state = DomainState(
        turn=0,
        grid_size=g,
        cop_position=list(config.cop_start),
        thief_position=list(config.thief_start),
        barriers=[],
        cop_barriers_remaining=config.max_barriers,
        move_history=[],
        cop_scent=[[0.0] * g for _ in range(g)],
        thief_scent=[[0.0] * g for _ in range(g)],
    )

    agent_belief = BeliefEngine(g, agent_role)
    policy.reset()
    cop_score = thief_score = 0
    last_event = ""

    while True:
        _clear()
        print("═" * 60)
        print(f"  COP vs THIEF — Human ({human_role.upper()}) vs Agent ({agent_role.upper()})")
        print(f"  Gamelet {gamelet_num}  |  Turn {state.turn + 1}/{config.max_moves}")
        print(f"  Score this gamelet — Cop: {cop_score}  Thief: {thief_score}")
        if last_event:
            print(f"  Last turn: {last_event}")
        print("═" * 60)
        print()
        print(_render_board(state, human_role, reveal, agent_belief, numeric))
        print()

        # Status info
        if human_role == "cop":
            print(f"  Your position: {tuple(state.cop_position)}  "
                  f"Barriers left: {state.cop_barriers_remaining}/{config.max_barriers}")
        else:
            print(f"  Your position: {tuple(state.thief_position)}  "
                  f"Survive {config.survival_threshold - state.turn} more turns to win")

        # Get both moves
        human_legal = _legal_moves_for(human_role, state)
        human_move = _get_human_move(human_legal, human_role)

        print(f"  Agent thinking", end="", flush=True)
        agent_move = _get_agent_move(agent_role, state, policy, agent_belief, gamelet_num)
        print(f"\r  Agent chose: {agent_move}      ")

        cop_move = human_move if human_role == "cop" else agent_move
        thief_move = human_move if human_role == "thief" else agent_move

        # Apply physics
        result = apply_joint_action(state, cop_move, thief_move, config)
        state = result.new_state
        cop_score += result.cop_score
        thief_score += result.thief_score

        # Update agent belief
        agent_scent = state.thief_scent if agent_role == "cop" else state.cop_scent
        agent_belief = (
            agent_belief
            .predict(list(state.barriers))
            .observe_scent(agent_scent, list(state.barriers))
            .step_complete(state.turn)
        )

        # Build event summary
        events = []
        if result.barrier_placed and result.barrier_position:
            events.append(f"barrier at {result.barrier_position}")
        if result.capture:
            events.append("CAPTURED!")
        elif result.trapped:
            events.append("TRAPPED!")
        events.append(f"cop→{tuple(state.cop_position)}  thief→{tuple(state.thief_position)}")
        last_event = "  ".join(events)

        if result.outcome != GameOutcome.ONGOING:
            break

    # Final screen
    _clear()
    print("═" * 60)
    outcome = result.outcome
    if outcome == GameOutcome.COP_WIN:
        winner = "COP wins"
        winner_label = "You win! 🎉" if human_role == "cop" else "Agent wins"
    elif outcome == GameOutcome.THIEF_WIN:
        winner = "THIEF wins (survived)"
        winner_label = "You win! 🎉" if human_role == "thief" else "Agent wins"
    else:
        winner = str(outcome.value)
        winner_label = ""

    print(f"  Gamelet {gamelet_num} over — {winner}  {winner_label}")
    print(f"  Final score — Cop: {cop_score}  Thief: {thief_score}")
    print("═" * 60)
    print()

    # Show full board on gamelet end
    reveal_final = True
    print(_render_board(state, human_role, reveal_final, agent_belief, numeric))
    print()
    input("  Press Enter for next gamelet...")
    return cop_score, thief_score, outcome.value


# ── Series ────────────────────────────────────────────────────────────────────

def _run_series(human_role: str, n_gamelets: int, reveal: bool, numeric: bool = False) -> None:
    agent_role = "thief" if human_role == "cop" else "cop"

    print(f"\n  Loading production {agent_role} policy...")
    manifest = REPO / "models" / "MANIFEST.json"
    if not manifest.exists():
        print(f"  ERROR: {manifest} not found. Run from the cop or thief repo root.")
        sys.exit(1)

    policy = load_recurrent_policy(manifest, agent_role)
    config = GameConfig()  # canonical Appendix-F config (6-gamelet series)

    scent_mode = "numeric floats" if numeric else "visual ░▒▓"
    print(f"  Policy loaded: {agent_role} ({policy.inference_mode})")
    print(f"\n  Rules:")
    print(f"    Grid: {config.grid_size}×{config.grid_size}")
    print(f"    Max turns per gamelet: {config.max_moves}")
    print(f"    Cop starts at {config.cop_start}, Thief at {config.thief_start}")
    print(f"    Cop wins by: capture or trapping the thief")
    print(f"    Thief wins by: surviving {config.survival_threshold} turns")
    print(f"    Cop barriers: {config.max_barriers} total per gamelet")
    print(f"    Scent display: {scent_mode}  (toggle with --numeric)")
    print(f"    Board legend: C=Cop  T=Thief  █=Barrier")
    if reveal:
        print(f"    --reveal: both positions shown (training/debug mode)")
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
        you = cop_wins
        agent = thief_wins
    else:
        you = thief_wins
        agent = cop_wins

    if you > agent:
        print("  You beat the agent! The strategy may have a weakness here.")
    elif agent > you:
        print("  Agent wins the series. Strategy appears strong.")
    else:
        print("  Tied series.")
    print("═" * 60)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Play against the production cop or thief AI policy.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--human-role",
        choices=["cop", "thief"],
        required=True,
        help="Which role you play (agent takes the other)",
    )
    parser.add_argument(
        "--reveal",
        action="store_true",
        help="Show both positions after each turn (removes hidden-info aspect)",
    )
    parser.add_argument(
        "--gamelets",
        type=int,
        default=3,
        metavar="N",
        help="Number of gamelets to play (default: 3)",
    )
    parser.add_argument(
        "--numeric",
        action="store_true",
        help="Show scent and belief as raw float values instead of ░▒▓ characters",
    )
    args = parser.parse_args()

    if args.gamelets < 1 or args.gamelets > 10:
        parser.error("--gamelets must be between 1 and 10")

    _run_series(args.human_role, args.gamelets, args.reveal, args.numeric)


if __name__ == "__main__":
    main()
