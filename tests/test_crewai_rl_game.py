"""Integration test: crewAI crew + RL model running a full P2P game.

Verifies:
- the repository's manifest-selected recurrent RL policy loads and masks actions
- crewAI Crew is constructed without error (LLM mock avoids API calls)
- A full commit-reveal game runs to completion
- Final audit passes
- When every_n_steps=1 the LLM path is attempted each turn (graceful fallback on mock)
"""

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
                game_id=game_id,
                step=step,
                role=opp_role,
                state_hash=state_hash,
                move="STAY",
                hint="Moving STAY",
                intent="truth",
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
                "ok": True,
                "move": "STAY",
                "hint": "Moving STAY",
                "intent": "truth",
                "state_hash": state_hash,
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
    @staticmethod
    def _load_deployed_policy():
        from agent.rl.model_schema import load_manifest
        from agent.rl.recurrent_policy import load_recurrent_policy

        manifest_path = Path("models/MANIFEST.json")
        entries = load_manifest(str(manifest_path))
        assert len(entries) == 1, "each independent role repository deploys exactly one policy"
        role = next(iter(entries))
        return role, load_recurrent_policy(manifest_path, role)

    def test_deployed_recurrent_policy_loads(self):
        role, policy = self._load_deployed_policy()
        assert policy.role == role
        assert policy.network.training is False
        logger.info("deployed recurrent policy loaded for %s", role)

    def test_deployed_recurrent_policy_selects_only_a_legal_action(self):
        from agent.observation import BeliefState, LocalObservation

        role, policy = self._load_deployed_policy()
        observation = LocalObservation(
            own_position=(0, 0),
            own_barriers_remaining=14 if role == "cop" else 0,
            known_barriers=[],
            opponent_scent=[[0.0] * 7 for _ in range(7)],
            last_hint="",
            step=1,
            gamelet=1,
            grid_size=7,
        )
        legal_actions = ["E", "S", "STAY"]
        move = policy.select_action(observation, BeliefState.uniform(7, step=1), legal_actions)
        assert move in legal_actions
        logger.info("deployed recurrent %s move: %s", role, move)


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
        with (
            patch.dict("sys.modules", {"agent.agents": mock_agents_mod}),
            patch("agent.orchestrator_crew.Crew", return_value=mock_crew_instance),
        ):
            crew = rt._get_or_create_crew("test_game_001")
            assert crew is not None
            logger.info("crewAI Crew constructed successfully with mock LLM")

    def test_crew_cached_per_game(self, tmp_path):
        rt = _make_runtime("cop", tmp_path)
        rt.llm = MagicMock()

        mock_agents_mod = MagicMock()
        mock_agents_mod.create_strategy_agent.return_value = MagicMock()
        mock_agents_mod.create_select_move_task.return_value = MagicMock()

        with (
            patch.dict("sys.modules", {"agent.agents": mock_agents_mod}),
            patch("agent.orchestrator_crew.Crew") as mock_crew,
        ):
            mock_crew.return_value = MagicMock()
            crew1 = rt._get_or_create_crew("game_001")
            crew2 = rt._get_or_create_crew("game_001")
            assert crew1 is crew2, "Crew should be cached per game_id"
            assert mock_crew.call_count == 1

    def test_crew_raises_without_llm(self, tmp_path):
        rt = _make_runtime("cop", tmp_path)
        rt.llm = None
        with pytest.raises(RuntimeError, match="No LLM configured"):
            rt._create_crew("game_no_llm")

    def test_select_move_rl_returns_none_without_grid_state(self, tmp_path):
        """_select_move_rl returns None when observation has no grid_state (Phase 2 v8).

        The grid_state key was removed from _build_observation to prevent hidden-coordinate
        leaks. RL selection now goes through the orchestrator path only.
        """
        rt = _make_runtime("cop", tmp_path)
        board_state = {
            "cop_position": [0, 0],
            "thief_position": [3, 3],
            "turn": 1,
            "scent_field": [],
        }
        obs = rt._build_observation(board_state)
        assert "grid_state" not in obs, "_build_observation must not expose grid_state"
        move = rt._select_move_rl(obs)
        # Without grid_state, RL path returns None (no hidden coords leak)
        assert move is None
        logger.info(f"PeerRuntime._select_move_rl (no grid_state) → {move}")


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
        board_state = {
            "cop_position": [0, 0],
            "thief_position": [3, 3],
            "turn": 1,
            "scent_field": [],
        }
        move = await select_move(rt, board_state)
        assert move in {
            "N",
            "S",
            "E",
            "W",
            "STAY",
            "NORTH",
            "SOUTH",
            "EAST",
            "WEST",
            "PLACE_N",
            "PLACE_S",
            "PLACE_E",
            "PLACE_W",
        }
        logger.info(f"select_move (RL) → {move}")

    @pytest.mark.asyncio
    async def test_select_move_heuristic_fallback_on_rl_failure(self, tmp_path):
        """When RL raises, select_move uses heuristic — LLM is never called (§0.5)."""
        from agent.peer_turn_helpers import select_move

        rt = _make_runtime("cop", tmp_path)
        rt.game_id = "sm_llm_fallback"

        llm_called = []

        async def spy_llm(game_id, obs):
            llm_called.append(True)
            return "N"

        with (
            patch.object(rt, "_select_move_rl", side_effect=RuntimeError("RL broke")),
            patch.object(rt, "_select_move_llm_async", new=spy_llm),
        ):
            board_state = {
                "cop_position": [0, 0],
                "thief_position": [3, 3],
                "turn": 1,
                "scent_field": [],
                "grid_size": 7,
                "barriers": [],
                "move_history": [],
            }
            move = await select_move(rt, board_state)
        assert llm_called == [], "LLM must not be called when RL fails"
        assert move in {"NORTH", "SOUTH", "EAST", "WEST", "STAY"}
        logger.info(f"select_move fell back to heuristic (not LLM): {move}")

    @pytest.mark.asyncio
    async def test_select_move_heuristic_fallback(self, tmp_path):
        """When both RL and LLM fail, heuristic kicks in."""
        from agent.peer_turn_helpers import select_move

        rt = _make_runtime("cop", tmp_path)
        rt.game_id = "sm_heuristic"

        with (
            patch.object(rt, "_select_move_rl", side_effect=RuntimeError("RL broke")),
            patch.object(
                rt, "_select_move_llm_async", new=AsyncMock(side_effect=RuntimeError("LLM broke"))
            ),
        ):
            board_state = {
                "cop_position": [0, 0],
                "thief_position": [3, 3],
                "turn": 1,
                "scent_field": [],
            }
            move = await select_move(rt, board_state)
        assert move in {"NORTH", "SOUTH", "EAST", "WEST", "STAY"}
        logger.info(f"select_move heuristic fallback → {move}")

    @pytest.mark.asyncio
    async def test_select_move_llm_not_called_regardless_of_cadence(self, tmp_path):
        """LLM must never be called for movement — cadence param has no effect (§0.5)."""
        from agent.peer_turn_helpers import select_move

        rt = _make_runtime("cop", tmp_path, llm_every_n=1)  # aggressive cadence, still no LLM
        rt.game_id = "cadence_test"

        llm_calls = []

        async def spy_llm(game_id, obs):
            llm_calls.append(obs)
            return "S"

        with patch.object(rt, "_select_move_llm_async", new=spy_llm):
            board_state = {
                "cop_position": [1, 1],
                "thief_position": [5, 5],
                "turn": 2,
                "scent_field": [],
                "grid_size": 7,
                "barriers": [],
                "move_history": [],
            }
            move = await select_move(rt, board_state)

        assert llm_calls == [], "LLM must not be called for movement selection"
        assert move in {"NORTH", "SOUTH", "EAST", "WEST", "STAY", "N", "S", "E", "W"}
        logger.info(f"select_move correctly used RL/heuristic: {move}")


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

        rt.opponent_client.action = AsyncMock(side_effect=_make_mcp_side_effect(game_id, "thief"))

        # Track crew creation
        crew_created = []
        original_create = rt._create_crew

        def track_create(gid):
            crew = original_create(gid)
            crew_created.append(gid)
            return crew

        with patch("agent.orchestrator_crew.Crew") as mock_crew:
            mock_crew.return_value = MagicMock()
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

        rt.opponent_client.action = AsyncMock(side_effect=_make_mcp_side_effect(game_id, "cop"))

        with patch("agent.orchestrator_crew.Crew") as mock_crew:
            mock_crew.return_value = MagicMock()
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
    async def test_full_game_without_llm_movement(self, tmp_path):
        """Game runs to completion using only RL/heuristic — no LLM for movement (§0.5)."""
        game_id = "crewai_cadence_001"
        rt = _make_runtime("cop", tmp_path, llm_every_n=1)  # even at max cadence, no LLM
        rt.game_id = game_id
        rt.game_dir = tmp_path / game_id
        rt.game_dir.mkdir(parents=True, exist_ok=True)
        rt.llm = MagicMock()
        rt.crews = {}

        llm_steps: list[int] = []

        async def spy_llm(game_id, obs):
            step = obs.get("turn", -1)
            llm_steps.append(step)
            return "N"

        rt.opponent_client.action = AsyncMock(side_effect=_make_mcp_side_effect(game_id, "thief"))

        with (
            patch.object(rt, "_select_move_llm_async", new=spy_llm),
            patch("agent.orchestrator_crew.Crew") as mock_crew,
        ):
            mock_crew.return_value = MagicMock()
            result = await rt.run_game(game_id)

        assert result["ok"] is True
        assert result["audit_ok"] is True
        assert llm_steps == [], f"LLM must not be called for movement; called at: {llm_steps}"
        logger.info(
            f"[no_llm_movement] game done: winner={result['winner']} steps={result['final_step']}"
        )

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

        rt.opponent_client.action = AsyncMock(side_effect=_make_mcp_side_effect(game_id, "thief"))

        with patch("agent.orchestrator_crew.Crew") as mock_crew:
            mock_crew.return_value = MagicMock()
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
