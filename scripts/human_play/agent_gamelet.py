"""One interactive gamelet of the human-vs-agent CLI."""

from __future__ import annotations

from agent.belief_engine import BeliefEngine
from agent.domain.config_validator import GameConfig
from agent.domain.transition import apply_joint_action
from agent.domain.types import DomainState
from agent.rules_outcomes import GameOutcome

from human_play.agent_board import _legal_moves_for, _render_board
from human_play.agent_moves import _get_agent_move, _get_human_move
from human_play.keys import _clear

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
            print(
                f"  Your position: {tuple(state.cop_position)}  "
                f"Barriers left: {state.cop_barriers_remaining}/{config.max_barriers}"
            )
        else:
            print(
                f"  Your position: {tuple(state.thief_position)}  "
                f"Survive {config.survival_threshold - state.turn} more turns to win"
            )

        # Get both moves
        human_legal = _legal_moves_for(human_role, state)
        human_move = _get_human_move(human_legal, human_role)

        print("  Agent thinking", end="", flush=True)
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
            agent_belief.predict(list(state.barriers))
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
