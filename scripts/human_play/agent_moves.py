"""Human keyboard move selection + agent policy move for the human-vs-agent CLI."""

from __future__ import annotations

import sys

from agent.belief_engine import BeliefEngine
from agent.domain.types import DomainState
from agent.observation import LocalObservation
from agent.rl.action_space import (
    COP_ACTIONS,
    THIEF_ACTIONS,
    compute_legal_mask_cop,
    compute_legal_mask_thief,
)

from human_play.keys import _CONTROLS_COP_BARRIER, _KEY_TO_MOVE, _KEY_TO_PLACE, _get_key

_CONTROLS_THIEF = "  ↑W  ↓S  ←A  →D  Space=STAY   Q/Esc=quit"
_CONTROLS_COP = "  ↑W  ↓S  ←A  →D  Space=STAY   B=barrier mode   Q/Esc=quit"


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
                print("\r  No barriers remaining.      ", end="", flush=True)
                continue

        # Cancel barrier mode
        if barrier_mode and key == "ESC":
            barrier_mode = False
            print(f"\r{_CONTROLS_COP}                              ", end="", flush=True)
            continue

        # Resolve action
        action = _KEY_TO_PLACE.get(key, "") if barrier_mode else _KEY_TO_MOVE.get(key, "")

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
            tuple(state.cop_position),
            state.barriers,
            state.cop_barriers_remaining,
            state.grid_size,
        )
        legal = [a for a, ok in zip(COP_ACTIONS, mask, strict=False) if ok]
        scent = state.thief_scent
    else:
        mask = compute_legal_mask_thief(
            tuple(state.thief_position),
            state.barriers,
            state.grid_size,
        )
        legal = [a for a, ok in zip(THIEF_ACTIONS, mask, strict=False) if ok]
        scent = state.cop_scent

    own_pos = tuple(state.cop_position) if agent_role == "cop" else tuple(state.thief_position)
    obs = LocalObservation(
        own_position=own_pos,
        own_barriers_remaining=state.cop_barriers_remaining if agent_role == "cop" else 0,
        known_barriers=list(state.barriers),
        opponent_scent=scent,
        last_hint="",
        step=state.turn,
        gamelet=gamelet,
        grid_size=state.grid_size,
    )
    return policy.select_action(obs, belief.belief, legal)
