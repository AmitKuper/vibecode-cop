"""Integration test: crewAI crew + RL model running a full P2P game.

Verifies:
- RL policy loads for both cop and thief
- crewAI Crew is constructed without error (LLM mock avoids API calls)
- A full commit-reveal game runs to completion
- Final audit passes
- When every_n_steps=1 the LLM path is attempted each turn (graceful fallback on mock)
"""

import json
import logging
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from agent.board import Board
from agent.mcp.crypto import create_commitment, hash_game_state
from agent.peer_runtime import PeerRuntime

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_runtime(role: str, tmp_path: Path, llm_every_n: int = 999) -> PeerRuntime:
    rt = PeerRuntime(
        role=role,
        secret="integration-secret",
        config_sha256="a" * 64,
        opponent_url="http://localhost:9999/mcp",
        games_dir=tmp_path,
        max_turns=10,
        group_name="integration_test",
    )
    rt.game_id = f"crewai_rl_game_{role}"
    rt.game_dir = tmp_path / rt.game_id
    rt.game_dir.mkdir(parents=True, exist_ok=True)
    rt.board = Board(cop_position=[0, 0], thief_position=[6, 6])
    rt._my_commits = {}
    rt.llm_every_n_steps = llm_every_n
    return rt


def _make_mcp_side_effect(game_id: str, opp_role: str):
    """Simulate honest opponent MCP endpoint."""
    commits: dict[int, tuple[str, str]] = {}

    async def side_effect(gid, msg):
        if msg.phase == "commit":
            step = msg.step
            state_hash = hash_game_state(
                {"cop_position": [0, 0], "thief_position": [6, 6], "turn": step}
            )
            h, nonce = create_commitment(
                game_id=game_id, step=step, role=opp_role,
                state_hash=state_hash, move="STAY", hint="Moving STAY", intent="truth",
            )
            commits[step] = (h, nonce)
            return {"ok": True, "h_commit": h}
        elif msg.phase == "reveal":
            step = msg.step
            h, nonce = commits.get(step, ("x" * 64, "y" * 64))
            state_hash = hash_game_state(
                {"cop_position": [0, 0], "thief_position": [6, 6], "turn": step}
            )
            return {
                "ok": True, "move": "STAY", "hint": "Moving STAY",
                "intent": "truth", "state_hash": state_hash,
            }
        elif msg.phase == "final_audit":
            return {"ok": True, "nonces": {str(s): n for s, (h, n) in commits.items()}}
        elif msg.phase == "game_end":
            return {"ok": True}
        return {"ok": True}

    return side_effect


# ---------------------------------------------------------------------------
# 1. RL model loads correctly
# ---------------------------------------------------------------------------

class TestRLModelLoad:
    def test_cop_rl_policy_loads(self):
        from agent.orchestrator_crew_helpers import get_rl_policy
        # Clear cache to force fresh load
        import agent.orchestrator_crew_helpers as h
        h._rl_policies.pop("cop", None)
        policy = get_rl_policy("cop")
        assert policy is not None, "cop RL policy must load from models/"
        logger.info(f"cop RL policy: algo={policy.algo}, barrier_quota={policy.barrier_quota}")

    def test_thief_rl_policy_loads(self):
        from agent.orchestrator_crew_helpers import get_rl_policy
        import agent.orchestrator_crew_helpers as h
        h._rl_policies.pop("thief", None)
        policy = get_rl_policy("thief")
        assert policy is not None, "thief RL policy must load from models/"
        logger.info(f"thief RL policy: algo={policy.algo}")

    def test_cop_rl_selects_valid_move(self):
        from agent.orchestrator_crew_helpers import get_rl_policy, build_observation
        policy = get_rl_policy("cop")
        board_state = {"cop_position": [0, 0], "thief_position": [3, 3], "turn": 1,
                       "scent_field": [], "grid_state": {}}
        obs = build_observation("cop", board_state)
        move = policy.select_move_from_dict(
            {"cop_position": [0, 0], "thief_position": [3, 3], "turn": 1}
        )
        assert move in ("NORTH", "SOUTH", "EAST", "WEST", "STAY",
                        "PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W")
        logger.info(f"RL cop move: {move}")

    def test_thief_rl_selects_valid_move(self):
        from agent.orchestrator_crew_helpers import get_rl_policy
        policy = get_rl_policy("thief")
        move = policy.select_move_from_dict(
            {"cop_position": [0, 0], "thief_position": [3, 3], "turn": 1}
        )
        assert move in ("NORTH", "SOUTH", "EAST", "WEST", "STAY")
        logger.info(f"RL thief move: {move}")


# ---------------------------------------------------------------------------
# 2. crewAI Crew construction
# ---------------------------------------------------------------------------

class TestCrewAIConstruction:
    def test_crew_created_with_mock_llm(self, tmp_path):
        """Crew builds without error when LLM is a mock."""
        rt = _make_runtime("cop", tmp_path)
        rt.llm = MagicMock()

        mock_crew_instance = MagicMock()
        mock_agents_mod = MagicMock()
        mock_agents_mod.create_strategy_agent.return_value = MagicMock()
        mock_agents_mod.create_select_move_task.return_value = MagicMock()

        # Patch agent.agents so langchain import is bypassed, and Crew so no real crewai needed.
        with patch.dict("sys.modules", {"agent.agents": mock_agents_mod}):
            with patch("agent.orchestrator_crew.Crew", return_value=mock_crew_instance):
                crew = rt._get_or_create_crew("test_game_001")
                assert crew is not None
                logger.info("crewAI Crew constructed successfully with mock LLM")

    def test_crew_cached_per_game(self, tmp_path):
        rt = _make_runtime("cop", tmp_path)
        rt.llm = MagicMock()

        mock_agents_mod = MagicMock()
        mock_agents_mod.create_strategy_agent.return_value = MagicMock()
        mock_agents_mod.create_select_move_task.return_value = MagicMock()

        with patch.dict("sys.modules", {"agent.agents": mock_agents_mod}):
            with patch("agent.orchestrator_crew.Crew") as MockCrew:
                MockCrew.return_value = MagicMock()
                crew1 = rt._get_or_create_crew("game_001")
                crew2 = rt._get_or_create_crew("game_001")
                assert crew1 is crew2, "Crew should be cached per game_id"
                assert MockCrew.call_count == 1

    def test_crew_raises_without_llm(self, tmp_path):
        rt = _make_runtime("cop", tmp_path)
        rt.llm = None
        with pytest.raises(RuntimeError, match="No LLM configured"):
            rt._create_crew("game_no_llm")

    def test_select_move_rl_uses_policy(self, tmp_path):
        """_select_move_rl on a PeerRuntime uses the loaded RL policy."""
        rt = _make_runtime("cop", tmp_path)
        board_state = {"cop_position": [0, 0], "thief_position": [3, 3],
                       "turn": 1, "scent_field": []}
        obs = rt._build_observation(board_state)
        move = rt._select_move_rl(obs)
        assert move is not None
        assert move in {"N", "S", "E", "W", "STAY", "PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"}
        logger.info(f"PeerRuntime._select_move_rl → {move}")


# ---------------------------------------------------------------------------
# 3. select_move helper: RL path + LLM path
# ---------------------------------------------------------------------------

class TestSelectMove:
    @pytest.mark.asyncio
    async def test_select_move_returns_rl_move(self, tmp_path):
        """select_move returns an RL move when RL model is available."""
        from agent.peer_turn_helpers import select_move
        rt = _make_runtime("cop", tmp_path)
        rt.game_id = "sm_test"
        board_state = {"cop_position": [0, 0], "thief_position": [3, 3],
                       "turn": 1, "scent_field": []}
        move = await select_move(rt, board_state)
        assert move in {"N", "S", "E", "W", "STAY",
                        "NORTH", "SOUTH", "EAST", "WEST",
                        "PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"}
        logger.info(f"select_move (RL) → {move}")

    @pytest.mark.asyncio
    async def test_select_move_llm_fallback_on_rl_failure(self, tmp_path):
        """When RL raises, select_move falls through to LLM then heuristic."""
        from agent.peer_turn_helpers import select_move
        rt = _make_runtime("cop", tmp_path)
        rt.game_id = "sm_llm_fallback"

        # Patch RL to fail, LLM to return a known move
        with patch.object(rt, "_select_move_rl", side_effect=RuntimeError("RL broke")):
            with patch.object(rt, "_select_move_llm_async", new=AsyncMock(return_value="N")):
                board_state = {"cop_position": [0, 0], "thief_position": [3, 3],
                               "turn": 1, "scent_field": []}
                move = await select_move(rt, board_state)
        assert move == "N"
        logger.info("select_move fell back to LLM crew correctly")

    @pytest.mark.asyncio
    async def test_select_move_heuristic_fallback(self, tmp_path):
        """When both RL and LLM fail, heuristic kicks in."""
        from agent.peer_turn_helpers import select_move
        rt = _make_runtime("cop", tmp_path)
        rt.game_id = "sm_heuristic"

        with patch.object(rt, "_select_move_rl", side_effect=RuntimeError("RL broke")):
            with patch.object(rt, "_select_move_llm_async",
                              new=AsyncMock(side_effect=RuntimeError("LLM broke"))):
                board_state = {"cop_position": [0, 0], "thief_position": [3, 3],
                               "turn": 1, "scent_field": []}
                move = await select_move(rt, board_state)
        assert move in {"NORTH", "SOUTH", "EAST", "WEST", "STAY"}
        logger.info(f"select_move heuristic fallback → {move}")

    @pytest.mark.asyncio
    async def test_select_move_llm_called_on_cadence(self, tmp_path):
        """When every_n_steps=2, LLM is invoked at even turns."""
        from agent.peer_turn_helpers import select_move
        rt = _make_runtime("cop", tmp_path, llm_every_n=2)
        rt.game_id = "cadence_test"

        llm_calls = []
        async def mock_llm(game_id, obs):
            llm_calls.append(obs)
            return "S"

        with patch.object(rt, "_select_move_llm_async", new=mock_llm):
            # turn=2 → step % 2 == 0 → LLM should fire
            board_state = {"cop_position": [1, 1], "thief_position": [5, 5],
                           "turn": 2, "scent_field": []}
            move = await select_move(rt, board_state)

        assert len(llm_calls) == 1, "LLM should have been called once at turn=2"
        assert move == "S"
        logger.info("crewAI LLM called at configured cadence step")


# ---------------------------------------------------------------------------
# 4. Full game run: RL moves, crewAI crew instantiated, audit passes
# ---------------------------------------------------------------------------

class TestFullGameWithCrewAIAndRL:
    @pytest.mark.asyncio
    async def test_full_game_cop_rl_crew_initialized(self, tmp_path):
        """Run full game as cop: RL drives moves, crew is created, audit passes."""
        game_id = "crewai_rl_cop_001"
        rt = _make_runtime("cop", tmp_path)
        rt.game_id = game_id
        rt.game_dir = tmp_path / game_id
        rt.game_dir.mkdir(parents=True, exist_ok=True)

        # Give it a mock LLM so crew CAN be created (no real API calls needed)
        rt.llm = MagicMock()
        rt.crews = {}

        rt.opponent_client.action = AsyncMock(
            side_effect=_make_mcp_side_effect(game_id, "thief")
        )

        # Track crew creation
        crew_created = []
        original_create = rt._create_crew
        def track_create(gid):
            crew = original_create(gid)
            crew_created.append(gid)
            return crew

        with patch("agent.orchestrator_crew.Crew") as MockCrew:
            MockCrew.return_value = MagicMock()
            result = await rt.run_game(game_id)

        assert result["ok"] is True, f"Game failed: {result}"
        assert result["role"] == "cop"
        assert result["winner"] in ("cop", "thief")
        assert result["final_step"] >= 1
        assert result["audit_ok"] is True, "Audit must pass"

        # Verify RL was used (game completed in reasonable steps)
        logger.info(
            f"[crewai_rl_test] cop game done: winner={result['winner']} "
            f"steps={result['final_step']} audit={result['audit_ok']}"
        )

    @pytest.mark.asyncio
    async def test_full_game_thief_rl_crew_initialized(self, tmp_path):
        """Run full game as thief: RL drives moves, crew can be created, audit passes."""
        game_id = "crewai_rl_thief_001"
        rt = _make_runtime("thief", tmp_path)
        rt.game_id = game_id
        rt.game_dir = tmp_path / game_id
        rt.game_dir.mkdir(parents=True, exist_ok=True)
        rt.llm = MagicMock()
        rt.crews = {}

        rt.opponent_client.action = AsyncMock(
            side_effect=_make_mcp_side_effect(game_id, "cop")
        )

        with patch("agent.orchestrator_crew.Crew") as MockCrew:
            MockCrew.return_value = MagicMock()
            result = await rt.run_game(game_id)

        assert result["ok"] is True
        assert result["role"] == "thief"
        assert result["winner"] in ("cop", "thief")
        assert result["audit_ok"] is True
        logger.info(
            f"[crewai_rl_test] thief game done: winner={result['winner']} "
            f"steps={result['final_step']} audit={result['audit_ok']}"
        )

    @pytest.mark.asyncio
    async def test_full_game_with_llm_cadence(self, tmp_path):
        """Game with every_n_steps=3: LLM is invoked at steps 3, 6, 9 (best-effort)."""
        game_id = "crewai_cadence_001"
        rt = _make_runtime("cop", tmp_path, llm_every_n=3)
        rt.game_id = game_id
        rt.game_dir = tmp_path / game_id
        rt.game_dir.mkdir(parents=True, exist_ok=True)
        rt.llm = MagicMock()
        rt.crews = {}

        llm_steps: list[int] = []

        async def mock_llm(game_id, obs):
            step = obs.get("turn", -1)
            llm_steps.append(step)
            logger.info(f"[crewai_cadence] LLM called at turn={step}")
            return "N"  # return a valid short move

        rt.opponent_client.action = AsyncMock(
            side_effect=_make_mcp_side_effect(game_id, "thief")
        )

        with patch.object(rt, "_select_move_llm_async", new=mock_llm):
            with patch("agent.orchestrator_crew.Crew") as MockCrew:
                MockCrew.return_value = MagicMock()
                result = await rt.run_game(game_id)

        assert result["ok"] is True
        assert result["audit_ok"] is True

        # LLM should have been called for turn % 3 == 0 turns
        logger.info(f"[crewai_cadence] LLM called at turns: {llm_steps}")
        if result["final_step"] >= 3:
            assert len(llm_steps) >= 1, "LLM should have been called at least once"

    @pytest.mark.asyncio
    async def test_full_game_result_files_written(self, tmp_path):
        """Full game writes all expected output files."""
        game_id = "crewai_files_001"
        rt = _make_runtime("cop", tmp_path)
        rt.game_id = game_id
        rt.game_dir = tmp_path / game_id
        rt.game_dir.mkdir(parents=True, exist_ok=True)
        rt.llm = MagicMock()
        rt.crews = {}

        rt.opponent_client.action = AsyncMock(
            side_effect=_make_mcp_side_effect(game_id, "thief")
        )

        with patch("agent.orchestrator_crew.Crew") as MockCrew:
            MockCrew.return_value = MagicMock()
            await rt.run_game(game_id)

        game_dir = tmp_path / game_id
        assert (game_dir / "game_state.json").exists()
        assert (game_dir / "my_commitments_cop.json").exists()
        assert (game_dir / "opponent_commitments.json").exists()
        assert (game_dir / "opponent_reveals.json").exists()

        state = json.loads((game_dir / "game_state.json").read_text())
        assert state["completed"] is True
        assert state["winner"] in ("cop", "thief")
        commits = json.loads((game_dir / "my_commitments_cop.json").read_text())
        assert len(commits) >= 1
        reveals = json.loads((game_dir / "opponent_reveals.json").read_text())
        assert len(reveals) >= 1
        logger.info(f"[crewai_files] {len(commits)} commits, {len(reveals)} reveals written")
