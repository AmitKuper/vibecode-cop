"""Bridge the canonical pure transition into the legacy runtime board."""

from __future__ import annotations

from dataclasses import dataclass

from agent.domain.config_validator import GameConfig
from agent.domain.transition import TransitionResult, apply_joint_action
from agent.domain.types import DomainState


@dataclass(frozen=True)
class IllegalJointActionError(ValueError):
    roles: tuple[str, ...]
    cop_action: str
    thief_action: str

    def __str__(self) -> str:
        return (
            f"illegal {'/'.join(self.roles)} action: "
            f"cop={self.cop_action!r}, thief={self.thief_action!r}"
        )


def locked_config(runtime) -> GameConfig:
    """Return the immutable negotiated config, with explicit legacy-test compatibility."""
    value = getattr(runtime, "game_config", None)
    return value if isinstance(value, GameConfig) else GameConfig()


def state_from_runtime(runtime, rules) -> DomainState:
    existing = getattr(runtime, "_domain_state", None)
    if (
        isinstance(existing, DomainState)
        and existing.turn == runtime.board.turn
        and existing.cop_position == tuple(runtime.board.cop_position)
        and existing.thief_position == tuple(runtime.board.thief_position)
        and existing.barriers == [tuple(item) for item in runtime.board.barriers]
        and existing.cop_barriers_remaining == runtime._cop_barriers_remaining
    ):
        return existing
    board = runtime.board
    return DomainState(
        turn=board.turn,
        grid_size=board.grid_size,
        cop_position=tuple(board.cop_position),
        thief_position=tuple(board.thief_position),
        barriers=[tuple(item) for item in board.barriers],
        cop_barriers_remaining=runtime._cop_barriers_remaining,
        move_history=board.move_history,
        thief_scent=rules.get_scent_field(),
    )


def apply_runtime_transition(
    runtime, rules, cop_action: str, thief_action: str
) -> TransitionResult:
    """Validate once, then synchronize the canonical result into the runtime."""
    result = apply_joint_action(
        state_from_runtime(runtime, rules),
        cop_action,
        thief_action,
        config=locked_config(runtime),
    )
    illegal = tuple(
        role
        for role, legal in (("cop", result.cop_action_legal), ("thief", result.thief_action_legal))
        if not legal
    )
    if illegal:
        raise IllegalJointActionError(illegal, cop_action, thief_action)
    state = result.new_state
    runtime.board.cop_position = list(state.cop_position)
    runtime.board.thief_position = list(state.thief_position)
    runtime.board.barriers = [list(item) for item in state.barriers]
    runtime.board.turn = state.turn
    runtime.board.move_history = [item.model_dump() for item in state.move_history]
    runtime._cop_barriers_remaining = state.cop_barriers_remaining
    runtime._domain_state = state
    runtime._last_transition_result = result
    rules._scent_grid = [row[:] for row in state.thief_scent]
    return result


def legal_actions_for_role(runtime, rules, role: str) -> list[str]:
    """Derive the legal mask from the canonical transition without mutating state."""
    from agent.rl.action_space import COP_ACTIONS, THIEF_ACTIONS

    state = state_from_runtime(runtime, rules)
    config = locked_config(runtime)
    actions = COP_ACTIONS if role == "cop" else THIEF_ACTIONS
    results = (
        apply_joint_action(state, action, "STAY", config=config)
        if role == "cop"
        else apply_joint_action(state, "STAY", action, config=config)
        for action in actions
    )
    return [
        action
        for action, result in zip(actions, results, strict=True)
        if (result.cop_action_legal if role == "cop" else result.thief_action_legal)
    ]
