"""Board rendering + legal-move display for the human-vs-rl CLI."""

from __future__ import annotations

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.types import DomainState
from cop_worker.rl.action_space import (
    COP_ACTIONS,
    THIEF_ACTIONS,
    compute_legal_mask_cop,
    compute_legal_mask_thief,
)
from human_play.keys import _scent_ch

# ── Board rendering ───────────────────────────────────────────────────────────


def _render_board(
    state: DomainState,
    human_role: str,
    reveal: bool,
    agent_belief: BeliefEngine,
    numeric: bool,
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
    if human_role == "cop":  # noqa: SIM108
        scent = state.thief_scent
    else:
        scent = state.cop_scent

    col_header = "    " + "  ".join(str(x) for x in range(g))
    rows = [col_header, "    " + "─" * (g * 3 - 1)]

    for row in range(g):
        cells = [f"{row} │"]
        for col in range(g):
            pos = (col, row)
            if pos in barrier_set:
                ch = " █ "
            elif pos == cop_pos and (human_role == "cop" or reveal):
                ch = " C "
            elif pos == thief_pos and (human_role == "thief" or reveal):
                ch = " T "
            elif reveal and pos == cop_pos:
                ch = " c "
            elif reveal and pos == thief_pos:
                ch = " t "
            else:
                sv = scent[row][col] if scent else 0.0
                ch = (
                    f"{sv:4.2f}"
                    if numeric and sv > 0
                    else (f"{sv:4.2f}" if numeric else f"  {_scent_ch(sv)} ")
                )
            cells.append(ch)
        rows.append("".join(cells))

    # Belief heatmap — raw probabilities
    belief_grid = agent_belief.belief.prob
    rows.append("")
    rows.append("   Agent's belief of YOUR position (probability):")
    rows.append("    " + "  ".join(str(x) for x in range(g)))
    for row in range(g):
        cells = [f"{row}   "]
        for col in range(g):
            v = belief_grid[row][col]
            cells.append(f"{v:4.2f}")
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
            tuple(state.cop_position),
            state.barriers,
            state.cop_barriers_remaining,
            state.grid_size,
        )
        return [a for a, ok in zip(COP_ACTIONS, mask) if ok]  # noqa: B905
    else:
        mask = compute_legal_mask_thief(
            tuple(state.thief_position),
            state.barriers,
            state.grid_size,
        )
        return [a for a, ok in zip(THIEF_ACTIONS, mask) if ok]  # noqa: B905
