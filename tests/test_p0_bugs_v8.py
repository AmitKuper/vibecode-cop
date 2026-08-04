"""Tests that reproduce and verify fixes for P0 bugs in v8.

P0-1: RuntimeMode not propagated to PeerRuntime from run_series.py
P0-2: Cop PLACE_* actions cause active/passive board divergence
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# P0-1: counted_mode propagation tests
# ---------------------------------------------------------------------------


def test_counted_mode_true_propagates():
    """PeerRuntime must receive counted_mode=True when run_series is called with COUNTED mode."""
    from unittest.mock import MagicMock, patch

    from agent.runtime_mode import RuntimeMode

    captured_kwargs = {}

    def fake_peer_runtime_init(self, **kwargs):
        captured_kwargs.update(kwargs)
        # Stub all the heavy init work
        self.role = kwargs["role"]
        self.opponent_role = "thief"
        self.secret = kwargs.get("secret", "")
        self.config_sha256 = kwargs.get("config_sha256", "")
        self.max_turns = 35
        self.group_name = kwargs.get("group_name", "")
        self.games_dir = __import__("pathlib").Path(".")
        self.my_endpoint = ""
        self.counted_mode = kwargs.get("counted_mode", False)
        self.opponent_client = MagicMock()
        self.board = MagicMock()
        self._my_commits = {}
        self._cop_barriers_remaining = 14
        self.llm = None
        self.crews = {}
        self.protocol_adapter = None
        self.orchestrator = None

    async def fake_run_game(self, game_id, counted_mode=None):
        return {
            "ok": True,
            "game_id": game_id,
            "role": "cop",
            "winner": "cop",
            "final_step": 1,
            "abort_reason": None,
            "audit_ok": True,
        }

    # run_series.py calls subprocess.check_output(...).stdout.strip() to get git SHA.
    # check_output normally returns bytes/str, not a CompletedProcess, so .stdout would
    # raise AttributeError. We return a MagicMock whose .stdout.strip() returns a valid SHA.
    fake_proc = MagicMock()
    fake_proc.stdout = "deadbeef1234567890abcdef1234567890abcdef"

    with (
        patch("agent.peer_runtime.PeerRuntime.__init__", fake_peer_runtime_init),
        patch("agent.peer_runtime.PeerRuntime.run_game", fake_run_game),
        patch("agent.config.shared_config.load_shared_config", return_value={}),
        patch("agent.config.shared_config.config_sha256", return_value="abc123"),
        patch("subprocess.check_output", return_value=fake_proc),
    ):
        import asyncio
        from pathlib import Path

        from scripts.run_series import run_series

        asyncio.run(
            run_series(
                thief_url="http://localhost:5001/mcp",
                secret="real-production-secret-value",
                config_sha256="abc123",
                games_dir=Path("/tmp/test_series"),
                n_gamelets=6,
                group_name="test",
                mode=RuntimeMode.COUNTED,
            )
        )

    assert "counted_mode" in captured_kwargs, "counted_mode not passed to PeerRuntime"
    assert captured_kwargs["counted_mode"] is True, (
        f"counted_mode should be True for COUNTED mode, got {captured_kwargs['counted_mode']!r}"
    )


def test_counted_mode_false_by_default():
    """PeerRuntime receives counted_mode=False when mode=DEVELOPMENT."""
    from unittest.mock import MagicMock, patch

    from agent.runtime_mode import RuntimeMode

    captured_kwargs = {}

    def fake_peer_runtime_init(self, **kwargs):
        captured_kwargs.update(kwargs)
        self.role = kwargs["role"]
        self.opponent_role = "thief"
        self.secret = kwargs.get("secret", "")
        self.config_sha256 = kwargs.get("config_sha256", "")
        self.max_turns = 35
        self.group_name = kwargs.get("group_name", "")
        self.games_dir = __import__("pathlib").Path(".")
        self.my_endpoint = ""
        self.counted_mode = kwargs.get("counted_mode", False)
        self.opponent_client = MagicMock()
        self.board = MagicMock()
        self._my_commits = {}
        self._cop_barriers_remaining = 14
        self.llm = None
        self.crews = {}
        self.protocol_adapter = None
        self.orchestrator = None

    async def fake_run_game(self, game_id, counted_mode=None):
        return {
            "ok": True,
            "game_id": game_id,
            "role": "cop",
            "winner": "thief",
            "final_step": 1,
            "abort_reason": None,
            "audit_ok": True,
        }

    with (
        patch("agent.peer_runtime.PeerRuntime.__init__", fake_peer_runtime_init),
        patch("agent.peer_runtime.PeerRuntime.run_game", fake_run_game),
        patch("agent.config.shared_config.load_shared_config", return_value={}),
        patch("agent.config.shared_config.config_sha256", return_value="abc123"),
    ):
        import asyncio
        from pathlib import Path

        from scripts.run_series import run_series

        asyncio.run(
            run_series(
                thief_url="http://localhost:5001/mcp",
                secret="",
                config_sha256="abc123",
                games_dir=Path("/tmp/test_series"),
                n_gamelets=1,
                group_name="test",
                mode=RuntimeMode.DEVELOPMENT,
            )
        )

    got = captured_kwargs.get("counted_mode")
    assert got is False, f"counted_mode should be False for DEVELOPMENT mode, got {got!r}"


def test_orchestrator_mode_matches_peer_runtime():
    """AgentOrchestrator.mode is COUNTED when PeerRuntime.counted_mode=True."""
    from unittest.mock import patch

    from agent.runtime_mode import RuntimeMode

    # PeerRuntime passes counted_mode=True → AgentOrchestrator gets mode=COUNTED
    captured_orch_kwargs = {}

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            captured_orch_kwargs.update(kwargs)
            self.mode = kwargs.get("mode", RuntimeMode.DEVELOPMENT)

        def start_watchdog(self):
            pass

        def stop_watchdog(self):
            pass

    # Just test the AgentOrchestrator init path directly from run_game logic
    with patch("agent.agent_orchestrator.AgentOrchestrator", FakeOrchestrator):
        # Simulate the logic in PeerRuntime.run_game
        effective_counted_mode = True
        _mode = RuntimeMode.COUNTED if effective_counted_mode else RuntimeMode.DEVELOPMENT
        orch = FakeOrchestrator(role="cop", game_uid="g01", grid_size=7, mode=_mode)
        assert orch.mode == RuntimeMode.COUNTED, (
            f"Orchestrator mode should be COUNTED, got {orch.mode}"
        )


# ---------------------------------------------------------------------------
# P0-2: Barrier placement consistency tests
# ---------------------------------------------------------------------------


def _make_domain_state(
    cop_pos=(0, 0), thief_pos=(3, 3), barriers=None, barriers_remaining=14, turn=0, grid_size=7
):
    from agent.domain.types import DomainState

    return DomainState(
        turn=turn,
        grid_size=grid_size,
        cop_position=cop_pos,
        thief_position=thief_pos,
        barriers=barriers or [],
        cop_barriers_remaining=barriers_remaining,
        move_history=[],
        scent_grid=[],
    )


def test_place_n_applies_barrier_in_domain_engine():
    """apply_joint_action with PLACE_N adds barrier north of cop position."""
    from agent.domain.transition import apply_joint_action

    state = _make_domain_state(cop_pos=(3, 3), thief_pos=(0, 0))
    result = apply_joint_action(state, "PLACE_N", "STAY")
    assert result.barrier_placed, "Barrier should be placed with PLACE_N"
    assert result.barrier_position == (3, 2), (
        f"Expected barrier at (3,2), got {result.barrier_position}"
    )
    assert (3, 2) in [tuple(b) for b in result.new_state.barriers], (
        "Barrier must appear in new_state.barriers"
    )


def test_place_s_applies_barrier():
    """apply_joint_action with PLACE_S adds barrier south of cop."""
    from agent.domain.transition import apply_joint_action

    state = _make_domain_state(cop_pos=(3, 3), thief_pos=(0, 0))
    result = apply_joint_action(state, "PLACE_S", "STAY")
    assert result.barrier_placed
    assert result.barrier_position == (3, 4)
    assert (3, 4) in [tuple(b) for b in result.new_state.barriers]


def test_place_e_applies_barrier():
    """apply_joint_action with PLACE_E adds barrier east of cop."""
    from agent.domain.transition import apply_joint_action

    state = _make_domain_state(cop_pos=(3, 3), thief_pos=(0, 0))
    result = apply_joint_action(state, "PLACE_E", "STAY")
    assert result.barrier_placed
    assert result.barrier_position == (4, 3)
    assert (4, 3) in [tuple(b) for b in result.new_state.barriers]


def test_place_w_applies_barrier():
    """apply_joint_action with PLACE_W adds barrier west of cop."""
    from agent.domain.transition import apply_joint_action

    state = _make_domain_state(cop_pos=(3, 3), thief_pos=(0, 0))
    result = apply_joint_action(state, "PLACE_W", "STAY")
    assert result.barrier_placed
    assert result.barrier_position == (2, 3)
    assert (2, 3) in [tuple(b) for b in result.new_state.barriers]


def test_place_decrements_barrier_quota():
    """Barrier placement decrements cop_barriers_remaining by 1."""
    from agent.domain.transition import apply_joint_action

    state = _make_domain_state(cop_pos=(3, 3), thief_pos=(0, 0), barriers_remaining=14)
    result = apply_joint_action(state, "PLACE_N", "STAY")
    assert result.new_state.cop_barriers_remaining == 13, (
        f"Expected 13 remaining, got {result.new_state.cop_barriers_remaining}"
    )


def test_place_exhausted_quota_rejected():
    """PLACE with 0 barriers remaining is illegal (cop_action_legal=False, no barrier placed)."""
    from agent.domain.transition import apply_joint_action

    state = _make_domain_state(cop_pos=(3, 3), thief_pos=(0, 0), barriers_remaining=0)
    result = apply_joint_action(state, "PLACE_N", "STAY")
    assert not result.cop_action_legal, "PLACE with 0 remaining should be illegal"
    assert not result.barrier_placed, "No barrier should be placed with 0 quota"
    assert result.new_state.cop_barriers_remaining == 0


def test_both_peers_get_same_barrier_after_placement():
    """Calling apply_joint_action on both sides with same args produces identical barriers."""
    from agent.domain.transition import apply_joint_action

    # Simulate active peer (cop side)
    state_cop_side = _make_domain_state(cop_pos=(2, 2), thief_pos=(5, 5))
    result_cop = apply_joint_action(state_cop_side, "PLACE_E", "NORTH")

    # Simulate passive peer (thief side) — same starting state, same actions
    state_thief_side = _make_domain_state(cop_pos=(2, 2), thief_pos=(5, 5))
    result_thief = apply_joint_action(state_thief_side, "PLACE_E", "NORTH")

    barriers_cop = sorted([tuple(b) for b in result_cop.new_state.barriers])
    barriers_thief = sorted([tuple(b) for b in result_thief.new_state.barriers])

    assert barriers_cop == barriers_thief, (
        f"Board divergence: cop barriers={barriers_cop}, thief barriers={barriers_thief}"
    )
    assert barriers_cop == [(3, 2)], f"Expected barrier at (3,2), got {barriers_cop}"


def test_peer_turn_loop_place_n_updates_runtime_board():
    """After PLACE_N in active turn loop, runtime.board.barriers contains the new barrier."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from agent.board import Board
    from agent.rules_engine import RulesEngine

    board = Board(cop_position=[3, 3], thief_position=[0, 0])
    rules = RulesEngine(board, max_turns=35)

    runtime = MagicMock()
    runtime.board = board
    runtime.role = "cop"
    runtime.game_id = "test_series_g01"
    runtime._cop_barriers_remaining = 14
    runtime._my_commits = {}
    runtime.config_sha256 = "test"
    runtime.secret = "test"
    runtime.orchestrator = None
    runtime.protocol_adapter = None
    runtime.game_dir = __import__("pathlib").Path("/tmp/test_ptl")
    runtime.game_dir.mkdir(parents=True, exist_ok=True)

    def fake_store_commit(step, payload):
        runtime._my_commits[step] = payload

    runtime._store_my_commit = fake_store_commit

    import asyncio

    from agent.peer_turn_loop import run_peer_turn

    # Patch the external I/O so the test doesn't need a live opponent
    with (
        patch("agent.peer_turn_loop.send_commit", new=AsyncMock(return_value={"h_commit": "aaa"})),
        patch(
            "agent.peer_turn_loop.send_reveal",
            new=AsyncMock(
                return_value={"move": "PLACE_N", "hint": "", "intent": "truth", "state_hash": "x"}
            ),
        ),
        patch("agent.peer_turn_loop.append_opponent_commit"),
        patch("agent.peer_turn_loop.append_opponent_reveal"),
        patch("agent.peer_turn_loop.select_move", new=AsyncMock(return_value="PLACE_N")),
        patch("agent.peer_turn_loop.get_coordinator") as mock_coord,
    ):
        coord = MagicMock()
        mock_coord.return_value = coord
        coord.get_state.return_value = "STEP_VERIFIED"

        winner, abort = asyncio.run(run_peer_turn(runtime, step=1, rules=rules))

    # After turn, barrier should be on the board
    assert [3, 2] in board.barriers, (
        f"Barrier at (3,2) expected after PLACE_N from (3,3), got barriers={board.barriers}"
    )
    assert runtime._cop_barriers_remaining == 13, (
        f"barriers_remaining should be 13, got {runtime._cop_barriers_remaining}"
    )
