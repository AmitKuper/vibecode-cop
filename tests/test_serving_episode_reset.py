"""One sub-game is one episode, so serving must reset policy state between sub-games.

This guards a bug that survived every match we played, counted ones included:
``scripts/live_match_ref3.py::_play_subgame`` built an ``RLMover`` and never called
``policy.reset()``, so the GRU hidden state carried into sub-games 2..6 on a board that had
just been reset. Training always resets between episodes; serving never did. Nothing failed
loudly -- the policy simply played sub-games 2..6 mid-thought.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.counted_policy import load_counted_policy

GRID = 7
LEGAL = ["N", "S", "E", "W", "STAY"]


def _observation(step: int) -> LocalObservation:
    return LocalObservation(
        own_position=(0, 0),
        own_barriers_remaining=14,
        known_barriers=[],
        opponent_scent=[[0.0] * GRID for _ in range(GRID)],
        last_hint="",
        step=step,
        gamelet=1,
        grid_size=GRID,
    )


def test_reset_clears_recurrent_and_decoder_state() -> None:
    """The contract _play_subgame depends on: reset() really returns the policy to step 0."""
    policy = load_counted_policy(Path(__file__).parents[1] / "models" / "MANIFEST.json", "cop")

    assert policy._hidden is None
    for step in range(5):
        policy.select_action(_observation(step), BeliefState.uniform(GRID, step=step), LEGAL)
    assert policy._hidden is not None, "GRU carried no state -- this test would prove nothing"

    policy.reset()
    assert policy._hidden is None
    assert policy._decoder is None


def test_first_action_of_a_sub_game_is_independent_of_the_previous_one() -> None:
    """The observable symptom: without reset, an identical opening sees a different action."""
    manifest = Path(__file__).parents[1] / "models" / "MANIFEST.json"
    policy = load_counted_policy(manifest, "cop")

    fresh = policy.select_action(_observation(0), BeliefState.uniform(GRID, step=0), LEGAL)

    for step in range(1, 12):
        policy.select_action(_observation(step), BeliefState.uniform(GRID, step=step), LEGAL)
    policy.reset()
    after_reset = policy.select_action(_observation(0), BeliefState.uniform(GRID, step=0), LEGAL)

    assert after_reset == fresh


def test_play_subgame_resets_the_mover_before_the_first_turn() -> None:
    """Pins the call site itself: constructing an RLMover is not enough."""
    import importlib.util

    script = Path(__file__).parents[1] / "scripts" / "live_match_ref3.py"
    spec = importlib.util.spec_from_file_location("_live_match_ref3", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    source = inspect.getsource(module._play_subgame)
    construct = source.index("RLMover(")
    reset = source.index("policy.reset()")
    assert reset > construct, "reset() must follow the RLMover construction"
    # And it must happen before any turn is played, not after the loop.
    assert reset < source.index("for "), "reset() must precede the turn loop"


def test_worker_start_playing_resets_the_shared_policy() -> None:
    """The worker path shares one module-level policy across all six gamelets."""
    from cop_worker import mcp_server

    class _Spy:
        def __init__(self) -> None:
            self.resets = 0

        def reset(self) -> None:
            self.resets += 1

    spy = _Spy()
    saved_policy, saved_gamelets = mcp_server._POLICY, dict(mcp_server._GAMELETS)
    mcp_server._POLICY = spy
    mcp_server._GAMELETS.clear()
    try:
        terms = {
            "board_size": GRID,
            "smell_grid_size": 5,
            "decay_per_step": 0.1,
            "emit_intensity": 0.9,
            "max_steps": 35,
            "survival_threshold": 35,
            "barriers_max": 14,
            "num_games": 6,
        }
        for sub_game in (1, 2):
            mcp_server.start_gamelet(
                game_uid="uid-reset-test",
                sub_game_number=sub_game,
                terms=terms,
                opponent_group="sparring-match",
                role="police",
            )
            mcp_server.start_playing("uid-reset-test", sub_game)
        assert spy.resets == 2, "each sub-game must begin from a clean recurrent state"
    finally:
        mcp_server._POLICY = saved_policy
        mcp_server._GAMELETS.clear()
        mcp_server._GAMELETS.update(saved_gamelets)
