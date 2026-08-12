"""Shared terms, scripted policy, and gamelet builders for worker-sighting tests."""

from __future__ import annotations

from cop_worker.gamelet import Gamelet
from cop_worker.synthetic_belief import SyntheticBeliefProvider

VALID_TERMS = {
    "board_size": 7,
    "smell_grid_size": 5,
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "max_steps": 35,
    "survival_threshold": 35,
    "barriers_max": 14,
    "num_games": 6,
    "setting": "Haifa",
    "hint_max_words": 15,
    "axis_origin_corner": "top-left",
    "axis_start_index": 0,
    "thief_start": [3, 3],
    "cop_start": [0, 0],
}


class _ScriptedPolicy:
    """Returns a fixed sequence of policy action names, recording each observation."""

    def __init__(self, actions: list[str]) -> None:
        self._actions = list(actions)
        self.seen: list = []

    def select_action(self, obs, belief, legal_actions):  # noqa: ANN001, ARG002
        self.seen.append(obs)
        return self._actions.pop(0) if self._actions else "STAY"


def _make_gamelet(policy=None) -> Gamelet:
    g = Gamelet(
        game_uid="test-uid-0001",
        sub_game_number=1,
        terms=VALID_TERMS,
        opponent_group="group-B",
        role="police",
        belief_provider=SyntheticBeliefProvider(),
        policy=policy,
    )
    g.start_playing()
    return g


def _commit(g: Gamelet, step: int, smell_grid: dict | None = None) -> dict:
    payload = {"kind": "commit", "step": step, "commitment_hash": "0" * 64}
    if smell_grid is not None:
        payload["smell_grid"] = smell_grid
    return g.process_event("opponent_turn", payload)
