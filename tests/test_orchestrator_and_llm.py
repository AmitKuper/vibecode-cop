"""Tests for orchestrator modules and LLM utilities.

Covers:
- agent/orchestrator.py
- agent/orchestrator_audit.py
- agent/orchestrator_phase.py
- agent/orchestrator_game.py
- agent/orchestrator_crew.py
- agent/orchestrator_crew_helpers.py
- agent/orchestrator_discovery_mixin.py
- agent/orchestrator_discovery_render.py
- agent/orchestrator_discovery_validate.py
- agent/orchestrator_discovery_write.py
- agent/game_runner_turn.py
- agent/game_runner_audit.py
- agent/game_runner_reports.py
- agent/llm/token_counter.py
- agent/llm/factory.py
- agent/llm/providers.py
- agent/llm/config.py
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_SHA = "a" * 64


def _make_action_msg(phase="commit", step=1, **kwargs):
    from agent.mcp.messages import ActionMessage

    return ActionMessage(
        game_id="game-1",
        step=step,
        role="initiator",
        config_sha256=_SHA,
        timestamp="2024-01-01T00:00:00+00:00",
        phase=phase,
        **kwargs,
    )


def _make_start_msg(game_id="game-1"):
    from agent.mcp.messages import StartGameMessage

    return StartGameMessage(
        game_id=game_id,
        roles={"cop": "p1", "thief": "p2"},
        config_sha256=_SHA,
        protocol_version="1.0",
        endpoint="http://localhost:5000/mcp",
        timestamp="2024-01-01T00:00:00+00:00",
    )


# ===========================================================================
# agent/llm/config.py
# ===========================================================================


class TestLLMConfig:
    def test_to_dict(self):
        from agent.llm.config import LLMConfig, LLMProvider

        cfg = LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4")
        d = cfg.to_dict()
        assert d["provider"] == "openai"
        assert d["model"] == "gpt-4"
        assert "temperature" in d

    def test_from_dict_known_provider(self):
        from agent.llm.config import LLMConfigBuilder, LLMProvider

        cfg = LLMConfigBuilder.from_dict({"provider": "anthropic", "model": "claude-3"})
        assert cfg.provider == LLMProvider.ANTHROPIC
        assert cfg.model == "claude-3"

    def test_from_dict_unknown_provider_falls_back_to_ollama(self):
        from agent.llm.config import LLMConfigBuilder, LLMProvider

        cfg = LLMConfigBuilder.from_dict({"provider": "unknown_xyz"})
        assert cfg.provider == LLMProvider.OLLAMA

    def test_from_dict_defaults(self):
        from agent.llm.config import LLMConfigBuilder

        cfg = LLMConfigBuilder.from_dict({})
        assert cfg.model == "gemma3:4b"
        assert cfg.temperature == 0.7

    def test_ollama_builder(self):
        from agent.llm.config import LLMConfigBuilder, LLMProvider

        cfg = LLMConfigBuilder.ollama(model="llama2")
        assert cfg.provider == LLMProvider.OLLAMA
        assert cfg.model == "llama2"

    def test_openai_builder(self):
        from agent.llm.config import LLMConfigBuilder, LLMProvider

        cfg = LLMConfigBuilder.openai(model="gpt-3.5-turbo", api_key="k")
        assert cfg.provider == LLMProvider.OPENAI
        assert cfg.api_key == "k"

    def test_anthropic_builder(self):
        from agent.llm.config import LLMConfigBuilder, LLMProvider

        cfg = LLMConfigBuilder.anthropic(model="claude-3", api_key="anthro")
        assert cfg.provider == LLMProvider.ANTHROPIC

    def test_azure_builder(self):
        from agent.llm.config import LLMConfigBuilder, LLMProvider

        cfg = LLMConfigBuilder.azure(
            model="gpt-4", api_key="az", base_url="https://azure.example.com"
        )
        assert cfg.provider == LLMProvider.AZURE
        assert cfg.api_version == "2024-02-15-preview"


# ===========================================================================
# agent/llm/token_counter.py
# ===========================================================================


class TestTokenCounter:
    def test_initial_state(self):
        from agent.llm.token_counter import TokenCounter

        tc = TokenCounter()
        assert tc.total == 0
        s = tc.summary()
        assert s["prompt_tokens"] == 0
        assert s["completion_tokens"] == 0
        assert s["total_tokens"] == 0
        assert s["llm_calls"] == 0

    def test_record(self):
        from agent.llm.token_counter import TokenCounter

        tc = TokenCounter()
        tc.record(prompt_tokens=100, completion_tokens=50)
        assert tc.total == 150
        s = tc.summary()
        assert s["llm_calls"] == 1

    def test_record_multiple(self):
        from agent.llm.token_counter import TokenCounter

        tc = TokenCounter()
        tc.record(10, 5)
        tc.record(20, 10)
        assert tc.total == 45
        assert tc.summary()["llm_calls"] == 2

    def test_reset(self):
        from agent.llm.token_counter import TokenCounter

        tc = TokenCounter()
        tc.record(100, 50)
        tc.reset()
        assert tc.total == 0
        assert tc.summary()["llm_calls"] == 0

    def test_record_from_crew_output_with_usage_metrics(self):
        from agent.llm.token_counter import TokenCounter

        tc = TokenCounter()
        usage = MagicMock()
        usage.total_tokens = 300
        usage.prompt_tokens = 200
        usage.completion_tokens = 100
        result = MagicMock()
        result.token_usage = usage
        tc.record_from_crew_output(result)
        assert tc._prompt == 200
        assert tc._completion == 100

    def test_record_from_crew_output_dict_usage(self):
        from agent.llm.token_counter import TokenCounter

        tc = TokenCounter()
        result = MagicMock()
        result.token_usage = {"prompt_tokens": 50, "completion_tokens": 25}
        tc.record_from_crew_output(result)
        assert tc._prompt == 50
        assert tc._completion == 25

    def test_record_from_crew_output_no_usage_attr(self):
        from agent.llm.token_counter import TokenCounter

        tc = TokenCounter()
        # Object without token_usage attribute
        result = object()
        tc.record_from_crew_output(result)
        assert tc.total == 0

    def test_record_from_crew_output_none_usage(self):
        from agent.llm.token_counter import TokenCounter

        tc = TokenCounter()
        result = MagicMock()
        result.token_usage = None
        tc.record_from_crew_output(result)
        assert tc.total == 0

    def test_thread_safety(self):
        from agent.llm.token_counter import TokenCounter

        tc = TokenCounter()
        errors = []

        def _worker():
            try:
                for _ in range(100):
                    tc.record(1, 1)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert tc.total == 1000


# ===========================================================================
# agent/llm/providers.py
# ===========================================================================


class TestLLMProviders:
    def test_create_ollama(self):
        mock_llm_cls = MagicMock()
        mock_crewai = MagicMock()
        mock_crewai.LLM = mock_llm_cls
        with patch.dict("sys.modules", {"crewai": mock_crewai}):
            from importlib import reload
            import agent.llm.providers as prov
            reload(prov)
            from agent.llm.config import LLMConfigBuilder
            cfg = LLMConfigBuilder.ollama()
            prov.create_ollama(cfg)
        mock_llm_cls.assert_called_once()

    def test_create_anthropic_no_key_raises(self):
        mock_llm_cls = MagicMock()
        mock_crewai = MagicMock()
        mock_crewai.LLM = mock_llm_cls
        with patch.dict("sys.modules", {"crewai": mock_crewai}):
            from importlib import reload
            import agent.llm.providers as prov
            reload(prov)
            from agent.llm.config import LLMConfig, LLMProvider
            cfg = LLMConfig(provider=LLMProvider.ANTHROPIC, model="claude-3", api_key=None)
            import os
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with pytest.raises(ValueError, match="Anthropic API key"):
                prov.create_anthropic(cfg)

    def test_create_anthropic_with_key(self):
        mock_llm_cls = MagicMock()
        mock_crewai = MagicMock()
        mock_crewai.LLM = mock_llm_cls
        with patch.dict("sys.modules", {"crewai": mock_crewai}):
            from importlib import reload
            import agent.llm.providers as prov
            reload(prov)
            from agent.llm.config import LLMConfig, LLMProvider
            cfg = LLMConfig(provider=LLMProvider.ANTHROPIC, model="claude-3", api_key="secret")
            prov.create_anthropic(cfg)
        mock_llm_cls.assert_called_once()

    def test_create_openai_no_key_raises(self):
        mock_llm_cls = MagicMock()
        mock_crewai = MagicMock()
        mock_crewai.LLM = mock_llm_cls
        with patch.dict("sys.modules", {"crewai": mock_crewai}):
            from importlib import reload
            import agent.llm.providers as prov
            reload(prov)
            from agent.llm.config import LLMConfig, LLMProvider
            cfg = LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4", api_key=None)
            import os
            os.environ.pop("OPENAI_API_KEY", None)
            with pytest.raises(ValueError, match="OpenAI API key"):
                prov.create_openai(cfg)

    def test_create_openai_with_key(self):
        mock_llm_cls = MagicMock()
        mock_crewai = MagicMock()
        mock_crewai.LLM = mock_llm_cls
        with patch.dict("sys.modules", {"crewai": mock_crewai}):
            from importlib import reload
            import agent.llm.providers as prov
            reload(prov)
            from agent.llm.config import LLMConfig, LLMProvider
            cfg = LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4", api_key="openai-key")
            prov.create_openai(cfg)
        mock_llm_cls.assert_called_once()

    def test_create_azure_no_key_raises(self):
        mock_llm_cls = MagicMock()
        mock_crewai = MagicMock()
        mock_crewai.LLM = mock_llm_cls
        with patch.dict("sys.modules", {"crewai": mock_crewai}):
            from importlib import reload
            import agent.llm.providers as prov
            reload(prov)
            from agent.llm.config import LLMConfig, LLMProvider
            cfg = LLMConfig(
                provider=LLMProvider.AZURE, model="gpt-4", api_key=None, base_url="https://az"
            )
            import os
            os.environ.pop("AZURE_OPENAI_API_KEY", None)
            with pytest.raises(ValueError, match="Azure API key"):
                prov.create_azure(cfg)

    def test_create_azure_no_base_url_raises(self):
        mock_llm_cls = MagicMock()
        mock_crewai = MagicMock()
        mock_crewai.LLM = mock_llm_cls
        with patch.dict("sys.modules", {"crewai": mock_crewai}):
            from importlib import reload
            import agent.llm.providers as prov
            reload(prov)
            from agent.llm.config import LLMConfig, LLMProvider
            cfg = LLMConfig(
                provider=LLMProvider.AZURE, model="gpt-4", api_key="az-key", base_url=None
            )
            with pytest.raises(ValueError, match="Azure endpoint"):
                prov.create_azure(cfg)

    def test_create_azure_with_deployment_id(self):
        mock_llm_cls = MagicMock()
        mock_crewai = MagicMock()
        mock_crewai.LLM = mock_llm_cls
        with patch.dict("sys.modules", {"crewai": mock_crewai}):
            from importlib import reload
            import agent.llm.providers as prov
            reload(prov)
            from agent.llm.config import LLMConfig, LLMProvider
            cfg = LLMConfig(
                provider=LLMProvider.AZURE,
                model="gpt-4",
                api_key="az-key",
                base_url="https://az.example.com",
                deployment_id="my-deployment",
            )
            prov.create_azure(cfg)
        call_kwargs = mock_llm_cls.call_args[1]
        assert "my-deployment" in call_kwargs.get("model", "")


# ===========================================================================
# agent/llm/factory.py
# ===========================================================================


class TestLLMFactory:
    def test_create_llm_ollama(self):
        mock_ollama = MagicMock(return_value="ollama-llm")
        with patch("agent.llm.factory.create_ollama", mock_ollama):
            from agent.llm.config import LLMConfigBuilder
            from agent.llm.factory import LLMFactory

            cfg = LLMConfigBuilder.ollama()
            result = LLMFactory.create_llm(cfg)
            assert result == "ollama-llm"

    def test_create_llm_openai(self):
        mock_openai = MagicMock(return_value="openai-llm")
        with patch("agent.llm.factory.create_openai", mock_openai):
            from agent.llm.config import LLMConfigBuilder
            from agent.llm.factory import LLMFactory

            cfg = LLMConfigBuilder.openai()
            result = LLMFactory.create_llm(cfg)
            assert result == "openai-llm"

    def test_create_llm_anthropic(self):
        mock_anthro = MagicMock(return_value="anthropic-llm")
        with patch("agent.llm.factory.create_anthropic", mock_anthro):
            from agent.llm.config import LLMConfigBuilder
            from agent.llm.factory import LLMFactory

            cfg = LLMConfigBuilder.anthropic()
            result = LLMFactory.create_llm(cfg)
            assert result == "anthropic-llm"

    def test_create_llm_azure(self):
        mock_azure = MagicMock(return_value="azure-llm")
        with patch("agent.llm.factory.create_azure", mock_azure):
            from agent.llm.config import LLMConfigBuilder
            from agent.llm.factory import LLMFactory

            cfg = LLMConfigBuilder.azure(
                model="gpt-4", api_key="k", base_url="https://az.example.com"
            )
            result = LLMFactory.create_llm(cfg)
            assert result == "azure-llm"

    def test_create_from_dict(self):
        mock_create = MagicMock(return_value="llm-from-dict")
        with patch("agent.llm.factory.LLMFactory.create_llm", mock_create):
            from agent.llm.factory import LLMFactory

            result = LLMFactory.create_from_dict({"provider": "ollama", "model": "llama2"})
            assert result == "llm-from-dict"

    def test_create_from_env_ollama(self):
        mock_create = MagicMock(return_value="env-llm")
        with patch("agent.llm.factory.LLMFactory.create_llm", mock_create), patch.dict(
            "os.environ", {"LLM_PROVIDER": "ollama", "LLM_MODEL": "llama2"}, clear=False
        ):
            from agent.llm.factory import LLMFactory

            result = LLMFactory.create_from_env()
            assert result == "env-llm"

    def test_create_from_env_openai(self):
        mock_create = MagicMock(return_value="env-llm")
        with patch("agent.llm.factory.LLMFactory.create_llm", mock_create), patch.dict(
            "os.environ",
            {"LLM_PROVIDER": "openai", "LLM_MODEL": "gpt-4", "OPENAI_API_KEY": "k"},
            clear=False,
        ):
            from agent.llm.factory import LLMFactory

            result = LLMFactory.create_from_env()
            assert result == "env-llm"

    def test_create_from_env_anthropic(self):
        mock_create = MagicMock(return_value="env-llm")
        with patch("agent.llm.factory.LLMFactory.create_llm", mock_create), patch.dict(
            "os.environ",
            {"LLM_PROVIDER": "anthropic", "LLM_MODEL": "claude-3", "ANTHROPIC_API_KEY": "k"},
            clear=False,
        ):
            from agent.llm.factory import LLMFactory

            result = LLMFactory.create_from_env()
            assert result == "env-llm"

    def test_create_from_env_azure(self):
        mock_create = MagicMock(return_value="env-llm")
        with patch("agent.llm.factory.LLMFactory.create_llm", mock_create), patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "azure",
                "LLM_MODEL": "gpt-4",
                "AZURE_OPENAI_API_KEY": "k",
                "LLM_BASE_URL": "https://az",
            },
            clear=False,
        ):
            from agent.llm.factory import LLMFactory

            result = LLMFactory.create_from_env()
            assert result == "env-llm"

    def test_create_from_env_unknown_falls_back(self):
        mock_create = MagicMock(return_value="fallback-llm")
        with patch("agent.llm.factory.LLMFactory.create_llm", mock_create), patch.dict(
            "os.environ", {"LLM_PROVIDER": "unknown_xyz"}, clear=False
        ):
            from agent.llm.factory import LLMFactory

            result = LLMFactory.create_from_env()
            assert result == "fallback-llm"


# ===========================================================================
# agent/orchestrator_crew_helpers.py
# ===========================================================================


class TestCrewHelpers:
    def test_parse_move_exact(self):
        from agent.orchestrator_crew_helpers import parse_move

        assert parse_move("N", ["N", "S", "E"]) == "N"

    def test_parse_move_long_form(self):
        from agent.orchestrator_crew_helpers import parse_move

        assert parse_move("NORTH", ["N", "S"]) == "N"

    def test_parse_move_token_in_text(self):
        from agent.orchestrator_crew_helpers import parse_move

        assert parse_move("I'll move EAST today", ["E", "W"]) == "E"

    def test_parse_move_no_valid_raises(self):
        from agent.orchestrator_crew_helpers import parse_move

        with pytest.raises(ValueError, match="No valid move"):
            parse_move("jump over the wall", ["N", "S"])

    def test_build_observation_cop(self):
        from agent.orchestrator_crew_helpers import build_observation

        state = {"cop_position": [1, 2], "thief_position": [4, 5], "turn": 3, "scent_field": [1]}
        obs = build_observation("cop", state)
        assert obs["own_position"] == [1, 2]
        assert "scent_field" in obs
        assert "candidate_actions" in obs
        assert "thief_position" not in obs

    def test_build_observation_thief(self):
        from agent.orchestrator_crew_helpers import build_observation

        state = {
            "cop_position": [1, 2],
            "thief_position": [4, 5],
            "turn": 5,
            "last_revealed_cop_pos": [1, 2],
        }
        obs = build_observation("thief", state)
        assert obs["own_position"] == [4, 5]
        assert "cop_position" not in obs

    def test_build_observation_candidates_corner(self):
        from agent.orchestrator_crew_helpers import build_observation

        # Position [0, 0]: can only go E and S, plus STAY
        state = {"cop_position": [0, 0], "thief_position": [3, 3], "turn": 0}
        obs = build_observation("cop", state)
        cands = obs["candidate_actions"]
        assert "W" not in cands
        assert "N" not in cands
        assert "STAY" in cands

    def test_get_rl_policy_returns_none_when_unavailable(self):
        from agent.orchestrator_crew_helpers import _rl_policies, get_rl_policy

        # Clear cache and ensure it returns None when model not available
        _rl_policies.clear()
        # Patch the import inside the function so RLPolicy.load raises
        with patch.dict("sys.modules", {"agent.rl.policy": None}):
            result = get_rl_policy("cop_no_model")
        assert result is None

    def test_get_rl_policy_uses_cache(self):
        from agent.orchestrator_crew_helpers import _rl_policies, get_rl_policy

        _rl_policies["cop"] = "cached-policy"
        result = get_rl_policy("cop")
        assert result == "cached-policy"
        _rl_policies.clear()


# ===========================================================================
# agent/orchestrator_game.py  (GameStateMixin)
# ===========================================================================


class TestGameStateMixin:
    def _make_mixin(self, tmp_path, role="cop"):
        from agent.orchestrator_game import GameStateMixin

        obj = GameStateMixin.__new__(GameStateMixin)
        obj.games_dir = tmp_path
        obj.role = role
        return obj

    def test_load_game_state_missing_returns_default(self, tmp_path):
        mixin = self._make_mixin(tmp_path)
        state = mixin._load_game_state("no-game")
        assert state["step"] == 0
        assert "cop_position" in state

    def test_save_and_load_game_state(self, tmp_path):
        mixin = self._make_mixin(tmp_path)
        data = {"step": 5, "winner": "cop"}
        mixin._save_game_state("g1", data)
        loaded = mixin._load_game_state("g1")
        assert loaded["step"] == 5

    def test_save_game_state_returns_true(self, tmp_path):
        mixin = self._make_mixin(tmp_path)
        result = mixin._save_game_state("g1", {"step": 0})
        assert result is True

    def test_append_move(self, tmp_path):
        mixin = self._make_mixin(tmp_path)
        mixin._append_move("g1", 1, "N", "S")
        moves_file = tmp_path / "g1" / "moves.jsonl"
        assert moves_file.exists()
        line = json.loads(moves_file.read_text().strip())
        assert line["cop_move"] == "N"

    def test_save_commitment(self, tmp_path):
        mixin = self._make_mixin(tmp_path)
        mixin._save_commitment("g1", "cop", 1, "abc123")
        commit_file = tmp_path / "g1" / "commitments.json"
        data = json.loads(commit_file.read_text())
        assert data["cop"]["1"] == "abc123"

    def test_store_and_load_my_commitment_payload(self, tmp_path):
        mixin = self._make_mixin(tmp_path)
        payload = {
            "h_commit": "h",
            "nonce": "n",
            "move": "N",
            "hint": "x",
            "intent": "truth",
            "state_hash": "s",
        }
        mixin._store_my_commitment_payload("g1", 1, payload)
        loaded = mixin._load_my_commitment_payload("g1", 1)
        assert loaded["nonce"] == "n"

    def test_load_my_commitment_payload_missing(self, tmp_path):
        mixin = self._make_mixin(tmp_path)
        result = mixin._load_my_commitment_payload("no-game", 1)
        assert result is None

    def test_handle_reveal_no_commitment(self, tmp_path):
        mixin = self._make_mixin(tmp_path)
        msg = _make_action_msg("reveal", step=5)
        result = mixin._handle_reveal("g1", msg)
        assert result["ok"] is False
        assert "No stored commitment" in result["error"]

    def test_handle_reveal_with_commitment(self, tmp_path):
        mixin = self._make_mixin(tmp_path)
        payload = {
            "h_commit": "h" * 64,
            "nonce": "nonce123",
            "move": "N",
            "hint": "hint",
            "intent": "truth",
            "state_hash": "s" * 64,
        }
        mixin._store_my_commitment_payload("g1", 1, payload)
        msg = _make_action_msg("reveal", step=1)
        result = mixin._handle_reveal("g1", msg)
        assert result["ok"] is True
        assert result["move"] == "N"


# ===========================================================================
# agent/orchestrator_audit.py  (AuditMixin)
# ===========================================================================


class TestAuditMixin:
    def _make_mixin(self, tmp_path, role="cop"):
        from agent.orchestrator_audit import AuditMixin

        obj = AuditMixin.__new__(AuditMixin)
        obj.role = role
        obj.games_dir = tmp_path
        obj.config_sha256 = _SHA
        return obj

    def test_handle_final_audit_no_file(self, tmp_path):
        mixin = self._make_mixin(tmp_path)
        msg = _make_action_msg("final_audit")
        result = mixin._handle_final_audit("g1", msg)
        assert result["ok"] is True
        assert result["nonces"] == {}

    def test_handle_final_audit_with_file(self, tmp_path):
        mixin = self._make_mixin(tmp_path)
        game_dir = tmp_path / "g1"
        game_dir.mkdir()
        data = {"1": {"nonce": "nonce1"}, "2": {"nonce": "nonce2"}}
        (game_dir / "my_commitments_cop.json").write_text(json.dumps(data))
        msg = _make_action_msg("final_audit")
        result = mixin._handle_final_audit("g1", msg)
        assert result["ok"] is True
        assert result["nonces"]["1"] == "nonce1"
        assert len(result["nonces"]) == 2

    def test_handle_final_audit_bad_file(self, tmp_path):
        mixin = self._make_mixin(tmp_path)
        game_dir = tmp_path / "g1"
        game_dir.mkdir()
        # Write invalid JSON
        (game_dir / "my_commitments_cop.json").write_text("not-json")
        msg = _make_action_msg("final_audit")
        result = mixin._handle_final_audit("g1", msg)
        assert result["ok"] is False

    def test_handle_game_end_basic(self, tmp_path):
        """Test _handle_game_end returns correct result."""
        from agent.orchestrator_audit import AuditMixin

        obj = AuditMixin.__new__(AuditMixin)
        obj.role = "cop"
        obj.games_dir = tmp_path
        obj.config_sha256 = _SHA

        # Setup game state
        game_dir = tmp_path / "g1"
        game_dir.mkdir()
        state_file = game_dir / "game_state.json"
        state_file.write_text(json.dumps({"step": 5, "completed": False}))

        def _load(game_id):
            return json.loads(state_file.read_text())

        def _save(game_id, state):
            state_file.write_text(json.dumps(state))
            return True

        obj._load_game_state = _load
        obj._save_game_state = _save
        obj.generate_reports = AsyncMock()

        msg = _make_action_msg("game_end", reason="cop")
        result = obj._handle_game_end("g1", msg)
        assert result["ok"] is True
        assert result["winner"] == "cop"
        assert result["completed"] is True

    def test_handle_game_end_calls_cleanup(self, tmp_path):
        from agent.orchestrator_audit import AuditMixin

        obj = AuditMixin.__new__(AuditMixin)
        obj.role = "cop"
        obj.games_dir = tmp_path
        obj.config_sha256 = _SHA

        game_dir = tmp_path / "g2"
        game_dir.mkdir()
        state_file = game_dir / "game_state.json"
        state_file.write_text(json.dumps({"step": 0}))

        obj._load_game_state = lambda gid: json.loads(state_file.read_text())
        obj._save_game_state = lambda gid, s: state_file.write_text(json.dumps(s))

        cleanup_called = []
        obj.cleanup_skill = lambda gid: cleanup_called.append(gid)
        obj.generate_reports = AsyncMock()

        msg = _make_action_msg("game_end", reason="thief")
        result = obj._handle_game_end("g2", msg)
        assert "g2" in cleanup_called


# ===========================================================================
# agent/orchestrator_phase.py  (PhaseMixin)
# ===========================================================================


class TestPhaseMixin:
    def _make_mixin(self, tmp_path, role="cop"):
        from agent.orchestrator_phase import PhaseMixin

        obj = PhaseMixin.__new__(PhaseMixin)
        obj.role = role
        obj.games_dir = tmp_path
        return obj

    def _make_full_mixin(self, tmp_path, role="cop"):
        """Make a PhaseMixin with stub implementations of the other mixin methods."""
        from agent.orchestrator_phase import PhaseMixin

        obj = PhaseMixin.__new__(PhaseMixin)
        obj.role = role
        obj.games_dir = tmp_path
        # Stub out methods provided by other mixins
        obj._handle_commit = MagicMock(return_value={"ok": True, "phase": "commit"})
        obj._handle_reveal = MagicMock(return_value={"ok": True, "phase": "reveal"})
        obj._handle_final_audit = MagicMock(return_value={"ok": True, "nonces": {}})
        obj._handle_game_end = MagicMock(return_value={"ok": True, "phase": "game_end"})
        obj._save_game_state = MagicMock(return_value=True)
        obj._load_game_state = MagicMock(return_value={"step": 0, "completed": False})
        return obj

    def test_on_action_unknown_phase(self, tmp_path):
        mixin = self._make_full_mixin(tmp_path)
        mixin._load_game_state = MagicMock(return_value={"step": 0, "completed": False})
        msg = _make_action_msg("unknown_phase")
        result = mixin._on_action("g1", msg)
        assert result["ok"] is False
        assert "Unknown phase" in result["error"]

    def test_on_action_already_completed(self, tmp_path):
        mixin = self._make_full_mixin(tmp_path)
        mixin._load_game_state = MagicMock(return_value={"completed": True, "winner": "cop"})
        msg = _make_action_msg("commit")
        result = mixin._on_action("g1", msg)
        assert result["ok"] is False
        assert "completed" in result["error"].lower()

    def test_on_action_final_audit_allowed_when_completed(self, tmp_path):
        mixin = self._make_full_mixin(tmp_path)
        mixin._load_game_state = MagicMock(return_value={"completed": True, "winner": "cop"})
        msg = _make_action_msg("final_audit")
        result = mixin._on_action("g1", msg)
        assert result["ok"] is True

    def test_on_start_game(self, tmp_path):
        mixin = self._make_full_mixin(tmp_path)
        saved = {}
        mixin._save_game_state = lambda gid, state: saved.update({gid: state}) or True

        msg = _make_start_msg("gstart")
        with (
            patch("agent.peer_runtime._load_start_positions", return_value=([0, 0], [6, 6])),
            patch("agent.orchestrator_phase._is_reachable", return_value=False),
        ):
            result = mixin._on_start_game(msg)
        assert result["ok"] is True
        assert "gstart" in saved

    def test_is_reachable_unreachable(self):
        from agent.orchestrator_phase import _is_reachable

        # Should return False for an unreachable host
        result = _is_reachable("http://127.0.0.1:19999", timeout=0.1)
        assert result is False

    def test_on_start_game_error(self, tmp_path):
        mixin = self._make_full_mixin(tmp_path)
        mixin._save_game_state = MagicMock(side_effect=RuntimeError("disk full"))

        msg = _make_start_msg("gerr")
        with patch("agent.peer_runtime._load_start_positions", return_value=([0, 0], [6, 6])):
            result = mixin._on_start_game(msg)
        assert result["ok"] is False

    def test_on_action_dispatch_error(self, tmp_path):
        mixin = self._make_full_mixin(tmp_path)
        mixin._load_game_state = MagicMock(side_effect=RuntimeError("db error"))
        msg = _make_action_msg("commit")
        result = mixin._on_action("g1", msg)
        assert result["ok"] is False


# ===========================================================================
# agent/orchestrator_crew.py  (CrewMixin)
# ===========================================================================


class TestCrewMixin:
    def _make_mixin(self, role="cop", llm=None):
        from agent.orchestrator_crew import CrewMixin

        obj = CrewMixin.__new__(CrewMixin)
        obj.role = role
        obj.llm = llm or MagicMock()
        obj.crews = {}
        return obj

    def test_get_or_create_crew_creates_new(self):
        mixin = self._make_mixin()
        mock_crew = MagicMock()
        mixin._create_crew = MagicMock(return_value=mock_crew)
        result = mixin._get_or_create_crew("g1")
        assert result is mock_crew

    def test_get_or_create_crew_returns_existing(self):
        mixin = self._make_mixin()
        existing = MagicMock()
        mixin.crews["g1"] = existing
        result = mixin._get_or_create_crew("g1")
        assert result is existing

    def test_build_crew_inputs(self):
        mixin = self._make_mixin()
        obs = {
            "own_position": [1, 2],
            "turn": 3,
            "candidate_actions": ["N", "S"],
            "scent_field": [0.1],
            "grid_state": {"x": 1},
        }
        inputs = mixin._build_crew_inputs(obs, ["N", "S"])
        assert inputs["role"] == "cop"
        assert inputs["own_position"] == [1, 2]
        assert inputs["candidate_actions"] == ["N", "S"]

    def test_build_observation_delegates(self):
        mixin = self._make_mixin("thief")
        state = {"cop_position": [0, 0], "thief_position": [3, 3], "turn": 1}
        obs = mixin._build_observation(state)
        assert obs["own_position"] == [3, 3]

    def test_long_move_conversion(self):
        mixin = self._make_mixin()
        assert mixin._long_move("N") == "NORTH"
        assert mixin._long_move("STAY") == "STAY"

    def test_short_move_conversion(self):
        mixin = self._make_mixin()
        assert mixin._short_move("NORTH") == "N"
        assert mixin._short_move("STAY") == "STAY"

    def test_select_move_rl_no_policy(self):
        mixin = self._make_mixin()
        with patch("agent.orchestrator_crew.get_rl_policy", return_value=None):
            result = mixin._select_move_rl({"grid_state": {"x": 1}})
        assert result is None

    def test_select_move_rl_empty_board_state(self):
        mixin = self._make_mixin()
        mock_policy = MagicMock()
        with patch("agent.orchestrator_crew.get_rl_policy", return_value=mock_policy):
            result = mixin._select_move_rl({"grid_state": {}})
        assert result is None

    def test_select_move_rl_success(self):
        mixin = self._make_mixin()
        mock_policy = MagicMock()
        mock_policy.select_move_from_dict.return_value = "NORTH"
        with patch("agent.orchestrator_crew.get_rl_policy", return_value=mock_policy):
            obs = {
                "grid_state": {"cop_position": [0, 0]},
                "candidate_actions": ["N", "S", "E"],
            }
            result = mixin._select_move_rl(obs)
        assert result == "N"

    def test_select_move_rl_not_in_candidates(self):
        mixin = self._make_mixin()
        mock_policy = MagicMock()
        mock_policy.select_move_from_dict.return_value = "WEST"
        with patch("agent.orchestrator_crew.get_rl_policy", return_value=mock_policy):
            obs = {
                "grid_state": {"cop_position": [0, 0]},
                "candidate_actions": ["N", "S"],
            }
            result = mixin._select_move_rl(obs)
        # W not in candidates, should return first candidate
        assert result == "N"

    def test_select_move_rl_inference_error(self):
        mixin = self._make_mixin()
        mock_policy = MagicMock()
        mock_policy.select_move_from_dict.side_effect = RuntimeError("boom")
        with patch("agent.orchestrator_crew.get_rl_policy", return_value=mock_policy):
            obs = {
                "grid_state": {"cop_position": [0, 0]},
                "candidate_actions": ["N", "S"],
            }
            result = mixin._select_move_rl(obs)
        assert result is None

    def test_select_move_llm(self):
        mixin = self._make_mixin()
        mock_crew = MagicMock()
        crew_result = MagicMock()
        crew_result.raw = "N"
        mock_crew.kickoff.return_value = crew_result
        mixin._get_or_create_crew = MagicMock(return_value=mock_crew)

        mock_tc = MagicMock()
        mixin._get_token_counter = MagicMock(return_value=mock_tc)

        with patch("agent.orchestrator_crew.parse_move", return_value="N"):
            obs = {"candidate_actions": ["N", "S"], "grid_state": {}}
            result = mixin._select_move_llm("g1", obs)
        assert result == "N"

    async def test_select_move_llm_async(self):
        mixin = self._make_mixin()
        mock_crew = MagicMock()
        crew_result = MagicMock()
        crew_result.raw = "S"
        mock_crew.kickoff_async = AsyncMock(return_value=crew_result)
        mixin._get_or_create_crew = MagicMock(return_value=mock_crew)

        mock_tc = MagicMock()
        mixin._get_token_counter = MagicMock(return_value=mock_tc)

        with patch("agent.orchestrator_crew.parse_move", return_value="S"):
            obs = {"candidate_actions": ["N", "S"], "grid_state": {}}
            result = await mixin._select_move_llm_async("g1", obs)
        assert result == "S"

    def test_create_crew_no_crewai(self):
        mixin = self._make_mixin()
        with patch("agent.orchestrator_crew.Crew", None):
            with pytest.raises(RuntimeError, match="crewai is not installed"):
                mixin._create_crew("g1")

    def test_create_crew_no_llm(self):
        mixin = self._make_mixin()
        mixin.llm = None
        mock_crew_cls = MagicMock()
        mock_agents_module = MagicMock()
        with (
            patch("agent.orchestrator_crew.Crew", mock_crew_cls),
            patch.dict("sys.modules", {"agent.agents": mock_agents_module}),
        ):
            with pytest.raises(RuntimeError, match="No LLM configured"):
                mixin._create_crew("g1")

    def test_create_crew_success(self):
        mixin = self._make_mixin()
        mock_crew_instance = MagicMock()
        mock_crew_cls = MagicMock(return_value=mock_crew_instance)
        mock_agent = MagicMock()
        mock_task = MagicMock()

        mock_agents_module = MagicMock()
        mock_agents_module.create_strategy_agent = MagicMock(return_value=mock_agent)
        mock_agents_module.create_select_move_task = MagicMock(return_value=mock_task)

        with (
            patch("agent.orchestrator_crew.Crew", mock_crew_cls),
            patch.dict("sys.modules", {"agent.agents": mock_agents_module}),
        ):
            crew = mixin._create_crew("g1")
        assert crew is mock_crew_instance
        assert mixin.crews["g1"] is mock_crew_instance

    def test_get_token_counter_cached(self):
        mixin = self._make_mixin()
        tc1 = mixin._get_token_counter()
        tc2 = mixin._get_token_counter()
        assert tc1 is tc2


# ===========================================================================
# agent/orchestrator_discovery_render.py
# ===========================================================================


class TestDiscoveryRender:
    def test_skill_module_name(self):
        from agent.orchestrator_discovery_render import _skill_module_name

        name = _skill_module_name("game-123")
        assert "game_" in name
        assert "-" not in name

    def test_skill_path(self):
        from agent.orchestrator_discovery_render import _skill_path

        p = _skill_path("game-abc")
        assert p.suffix == ".py"
        assert "game_abc" in p.name

    def test_render_skill_no_remap(self):
        from agent.orchestrator_discovery_render import _render_skill

        code = _render_skill(
            transport_url="http://example.com/sse",
            start_tool="start_game",
            start_msg="message_json",
            start_sig=None,
            action_tool="action",
            act_gid="game_id",
            act_msg="message_json",
            act_sig=None,
            ping_tool="ping",
        )
        assert "start_game" in code
        assert "action" in code
        assert "ping" in code
        assert "FIELD_MAP = {}" in code

    def test_render_skill_with_remap(self):
        from agent.orchestrator_discovery_render import _render_skill

        code = _render_skill(
            transport_url="http://example.com/sse",
            start_tool="start_game",
            start_msg="msg",
            start_sig="sig",
            action_tool="action",
            act_gid="gid",
            act_msg="msg",
            act_sig="sig",
            ping_tool="ping",
            field_map={"game_id": "gameId", "step": "stepNo"},
        )
        assert "FIELD_MAP" in code
        assert "_remap" in code

    def test_render_skill_with_signing(self):
        from agent.orchestrator_discovery_render import _render_skill

        code = _render_skill(
            transport_url="http://example.com/sse",
            start_tool="start_game",
            start_msg="msg",
            start_sig="signature",
            action_tool="action",
            act_gid="game_id",
            act_msg="msg",
            act_sig="signature",
            ping_tool="ping",
        )
        assert "sign_message" in code
        assert "canonical_json" in code


# ===========================================================================
# agent/orchestrator_discovery_validate.py
# ===========================================================================


class TestDiscoveryValidate:
    def test_python_validate_skill_valid(self, tmp_path):
        from agent.orchestrator_discovery_validate import python_validate_skill

        skill = tmp_path / "skill.py"
        skill.write_text(
            "async def start_game(d): pass\n"
            "async def action(g, d): pass\n"
            "async def ping(): pass\n"
        )
        valid, issues = python_validate_skill(skill)
        assert valid
        assert not issues

    def test_python_validate_skill_missing_function(self, tmp_path):
        from agent.orchestrator_discovery_validate import python_validate_skill

        skill = tmp_path / "skill.py"
        skill.write_text("async def start_game(d): pass\n")
        valid, issues = python_validate_skill(skill)
        assert not valid
        assert any("action" in i for i in issues)

    def test_python_validate_skill_not_found(self, tmp_path):
        from agent.orchestrator_discovery_validate import python_validate_skill

        valid, issues = python_validate_skill(tmp_path / "nonexistent.py")
        assert not valid
        assert any("not found" in i.lower() for i in issues)

    def test_python_validate_skill_syntax_error(self, tmp_path):
        from agent.orchestrator_discovery_validate import python_validate_skill

        skill = tmp_path / "bad.py"
        # Write invalid Python syntax
        skill.write_bytes(b"def start_game(\n  x:\n")
        valid, issues = python_validate_skill(skill)
        assert not valid

    def test_run_validator_crew_falls_back_to_python(self, tmp_path):
        from agent.orchestrator_discovery_validate import run_validator_crew

        skill = tmp_path / "skill.py"
        skill.write_text(
            "async def start_game(d): pass\n"
            "async def action(g, d): pass\n"
            "async def ping(): pass\n"
        )
        # Make crewai import fail — Crew is imported inside the try block
        with patch.dict("sys.modules", {"crewai": None}):
            valid, issues = run_validator_crew("cop", None, skill)
        assert valid

    def test_validate_skill_loop_passes_first_attempt(self, tmp_path):
        from agent.orchestrator_discovery_validate import validate_skill_loop

        skill = tmp_path / "skill.py"
        skill.write_text(
            "async def start_game(d): pass\n"
            "async def action(g, d): pass\n"
            "async def ping(): pass\n"
        )

        with patch(
            "agent.orchestrator_discovery_validate.run_validator_crew", return_value=(True, [])
        ):
            result = validate_skill_loop(
                "cop", None, "g1", skill, "http://x", {}, "", None, lambda *a: None
            )
        assert result == skill

    def test_validate_skill_loop_regenerates(self, tmp_path):
        from agent.orchestrator_discovery_validate import validate_skill_loop

        skill = tmp_path / "skill.py"
        skill.write_text("# empty")

        write_calls = []

        def _write(*args):
            write_calls.append(args)

        with patch(
            "agent.orchestrator_discovery_validate.run_validator_crew",
            side_effect=[(False, ["Missing action"]), (True, [])],
        ):
            result = validate_skill_loop(
                "cop", None, "g1", skill, "http://x", {}, "", None, _write
            )
        assert len(write_calls) == 1


# ===========================================================================
# agent/orchestrator_discovery_write.py
# ===========================================================================


class TestDiscoveryWrite:
    def test_parse_explorer_mapping_json(self):
        from agent.orchestrator_discovery_write import _parse_explorer_mapping

        raw = json.dumps({"start_game_tool": "start", "action_tool": "act"})
        result = _parse_explorer_mapping(raw)
        assert result["start_game_tool"] == "start"

    def test_parse_explorer_mapping_embedded_json(self):
        from agent.orchestrator_discovery_write import _parse_explorer_mapping

        raw = 'Some text {"start_game_tool": "start", "action_tool": "act"} more text'
        result = _parse_explorer_mapping(raw)
        assert result["action_tool"] == "act"

    def test_parse_explorer_mapping_no_json_raises(self):
        from agent.orchestrator_discovery_write import _parse_explorer_mapping

        with pytest.raises(ValueError, match="No valid JSON"):
            _parse_explorer_mapping("plain text no json here")

    def test_write_skill_from_mapping(self, tmp_path):
        from agent.orchestrator_discovery_write import _write_skill_from_mapping

        skill_path = tmp_path / "skill.py"
        mapping = {
            "start_game_tool": "start_game",
            "action_tool": "action",
            "ping_tool": "ping",
            "start_game_params": {"message_param": "msg"},
            "action_params": {"game_id_param": "gid", "message_param": "msg"},
            "signing_required": False,
            "payload_type": "string",
        }
        with patch("agent.orchestrator_discovery_write._SKILLS_DIR", tmp_path):
            _write_skill_from_mapping(skill_path, "http://x/sse", mapping)
        assert skill_path.exists()
        code = skill_path.read_text()
        assert "start_game" in code

    def test_write_skill_from_schemas(self, tmp_path):
        from agent.orchestrator_discovery_write import _write_skill_from_schemas

        skill_path = tmp_path / "skill.py"
        schemas = {
            "start_game": {
                "input_schema": {"properties": {"message_json": {"type": "string"}}}
            },
            "action": {
                "input_schema": {
                    "properties": {
                        "game_id": {},
                        "message_json": {"type": "string"},
                    }
                }
            },
            "ping": {"input_schema": {"properties": {}}},
        }
        with patch("agent.orchestrator_discovery_write._SKILLS_DIR", tmp_path):
            _write_skill_from_schemas(skill_path, "http://x/sse", schemas)
        assert skill_path.exists()

    def test_write_skill_from_schemas_with_protocol_def(self, tmp_path):
        from agent.orchestrator_discovery_write import _write_skill_from_schemas

        skill_path = tmp_path / "skill2.py"
        schemas = {}
        proto = {"fields": {"game_id": "gameId"}}
        with patch("agent.orchestrator_discovery_write._SKILLS_DIR", tmp_path):
            _write_skill_from_schemas(skill_path, "http://x/sse", schemas, proto)
        assert skill_path.exists()


# ===========================================================================
# agent/orchestrator_discovery_mixin.py  (DiscoveryMixin)
# ===========================================================================


class TestDiscoveryMixin:
    def _make_mixin(self, role="cop"):
        from agent.orchestrator_discovery_mixin import DiscoveryMixin

        obj = DiscoveryMixin.__new__(DiscoveryMixin)
        obj.role = role
        obj.llm = MagicMock()
        obj.secret = "test-secret"
        obj.protocol_model = {}
        obj.mcp_skill = None
        return obj

    def test_has_tool_false(self):
        mixin = self._make_mixin()
        assert mixin.has_tool("nonexistent") is False

    def test_cleanup_skill(self, tmp_path):
        mixin = self._make_mixin()
        mixin.mcp_skill = MagicMock()
        skill_path = tmp_path / "game_g1_mcp.py"
        skill_path.write_text("# skill")

        with (
            patch("agent.orchestrator_discovery_mixin._skill_path", return_value=skill_path),
            patch(
                "agent.orchestrator_discovery_mixin._skill_module_name",
                return_value="agent.skills.game_g1_mcp",
            ),
        ):
            mixin.cleanup_skill("g1")
        assert not skill_path.exists()
        assert mixin.mcp_skill is None

    def test_run_explorer_crew_no_llm(self):
        mixin = self._make_mixin()
        mixin.llm = None
        result = mixin._run_explorer_crew("http://example.com")
        assert result == ""

    def test_run_explorer_crew_exception(self):
        mixin = self._make_mixin()
        # Cause an exception in the try block by making crewai import fail
        with patch.dict("sys.modules", {"crewai": None}):
            result = mixin._run_explorer_crew("http://example.com")
        # Should fallback to empty string
        assert isinstance(result, str)

    def test_write_skill_uses_explorer_raw(self, tmp_path):
        mixin = self._make_mixin()
        skill_path = tmp_path / "skill.py"
        mock_write = MagicMock()
        with (
            patch(
                "agent.orchestrator_discovery_mixin._parse_explorer_mapping",
                return_value={
                    "start_game_tool": "start_game",
                    "action_tool": "action",
                    "field_map": {},
                    "transport_url": "http://x/sse",
                },
            ),
            patch(
                "agent.orchestrator_discovery_mixin._write_skill_from_mapping", mock_write
            ),
        ):
            mixin._write_skill(skill_path, "http://x/sse", {}, '{"some": "json"}', None)
        mock_write.assert_called_once()

    def test_write_skill_falls_back_to_schemas(self, tmp_path):
        mixin = self._make_mixin()
        skill_path = tmp_path / "skill.py"
        mock_write = MagicMock()
        with (
            patch(
                "agent.orchestrator_discovery_mixin._parse_explorer_mapping",
                side_effect=ValueError("bad"),
            ),
            patch(
                "agent.orchestrator_discovery_mixin._write_skill_from_schemas", mock_write
            ),
        ):
            mixin._write_skill(skill_path, "http://x/sse", {"ping": {}}, "bad json", None)
        mock_write.assert_called_once()

    def test_write_skill_no_explorer_raw(self, tmp_path):
        mixin = self._make_mixin()
        skill_path = tmp_path / "skill.py"
        mock_write = MagicMock()
        with patch(
            "agent.orchestrator_discovery_mixin._write_skill_from_schemas", mock_write
        ):
            mixin._write_skill(skill_path, "http://x/sse", {}, "", None)
        mock_write.assert_called_once()

    def test_probe_full(self):
        mixin = self._make_mixin()
        # _probe_sync is imported inside _probe_full from agent.tools.mcp_probe_tool
        # which has heavy crewai deps — inject directly into sys.modules
        mock_probe_module = MagicMock()
        mock_probe_module._probe_sync = MagicMock(
            return_value=("http://x/sse", {"tool1": {}}, {"version": "1"})
        )
        with patch.dict("sys.modules", {"agent.tools.mcp_probe_tool": mock_probe_module}):
            transport_url, schemas, proto = mixin._probe_full("http://x")
        assert transport_url == "http://x/sse"
        assert "tool1" in schemas


# ===========================================================================
# agent/orchestrator.py  (GameOrchestrator)
# ===========================================================================


class TestGameOrchestrator:
    def _make_orch(self, tmp_path, role="cop"):
        """Build a GameOrchestrator with all external deps mocked."""
        mock_mcp_server = MagicMock()
        mock_mcp_client = MagicMock()
        mock_protocol_discovery = MagicMock()

        with (
            patch("agent.orchestrator.AgentMCPServer", return_value=mock_mcp_server),
            patch("agent.orchestrator.GameMCPClient", return_value=mock_mcp_client),
            patch("agent.orchestrator.ProtocolDiscovery", return_value=mock_protocol_discovery),
            patch("agent.orchestrator.LLMFactory.create_from_env", return_value=MagicMock()),
        ):
            from agent.orchestrator import GameOrchestrator

            orch = GameOrchestrator(
                role=role,
                secret="secret",
                config_sha256=_SHA,
                games_dir=tmp_path,
            )
        return orch

    def test_init_cop(self, tmp_path):
        orch = self._make_orch(tmp_path, "cop")
        assert orch.role == "cop"
        assert orch.games_dir == tmp_path

    def test_init_thief(self, tmp_path):
        orch = self._make_orch(tmp_path, "thief")
        assert orch.role == "thief"

    def test_initialize_llm_with_config(self, tmp_path):
        from agent.llm.config import LLMConfigBuilder
        from agent.orchestrator import GameOrchestrator

        cfg = LLMConfigBuilder.ollama()
        mock_llm = MagicMock()
        with patch("agent.orchestrator.LLMFactory.create_llm", return_value=mock_llm):
            orch_stub = GameOrchestrator.__new__(GameOrchestrator)
            result = orch_stub._initialize_llm(cfg, None)
        assert result is mock_llm

    def test_initialize_llm_with_dict(self):
        from agent.orchestrator import GameOrchestrator

        mock_llm = MagicMock()
        with patch("agent.orchestrator.LLMFactory.create_from_dict", return_value=mock_llm):
            orch_stub = GameOrchestrator.__new__(GameOrchestrator)
            result = orch_stub._initialize_llm(None, {"provider": "ollama"})
        assert result is mock_llm

    def test_initialize_llm_from_env(self):
        from agent.orchestrator import GameOrchestrator

        mock_llm = MagicMock()
        with patch("agent.orchestrator.LLMFactory.create_from_env", return_value=mock_llm):
            orch_stub = GameOrchestrator.__new__(GameOrchestrator)
            result = orch_stub._initialize_llm(None, None)
        assert result is mock_llm

    def test_initialize_llm_exception_returns_none(self):
        from agent.orchestrator import GameOrchestrator

        with patch(
            "agent.orchestrator.LLMFactory.create_from_env", side_effect=Exception("no creds")
        ):
            orch_stub = GameOrchestrator.__new__(GameOrchestrator)
            result = orch_stub._initialize_llm(None, None)
        assert result is None

    async def test_run_async(self, tmp_path):
        orch = self._make_orch(tmp_path)
        orch.mcp_server.run_async = AsyncMock()
        await orch.run_async(host="localhost", port=9999)
        orch.mcp_server.run_async.assert_awaited_once_with(host="localhost", port=9999)

    def test_init_group_name(self, tmp_path):
        mock_mcp_server = MagicMock()
        mock_mcp_client = MagicMock()
        mock_protocol_discovery = MagicMock()
        with (
            patch("agent.orchestrator.AgentMCPServer", return_value=mock_mcp_server),
            patch("agent.orchestrator.GameMCPClient", return_value=mock_mcp_client),
            patch("agent.orchestrator.ProtocolDiscovery", return_value=mock_protocol_discovery),
            patch("agent.orchestrator.LLMFactory.create_from_env", return_value=MagicMock()),
        ):
            from agent.orchestrator import GameOrchestrator

            orch = GameOrchestrator(
                role="cop",
                secret="s",
                config_sha256=_SHA,
                games_dir=tmp_path,
                group_name="team-alpha",
            )
        assert orch.group_id == "team-alpha"


# ===========================================================================
# agent/game_runner_turn.py
# ===========================================================================


class TestGameRunnerTurn:
    def _make_runner(self, config_sha256=_SHA):
        runner = MagicMock()
        runner.config_sha256 = config_sha256
        runner._log_event = MagicMock()
        runner._cop_commits = {}
        runner._thief_commits = {}
        runner._cop_reveals = {}
        runner._thief_reveals = {}
        return runner

    async def test_request_commit_success(self):
        from agent.game_runner_turn import request_commit

        runner = self._make_runner()
        client = AsyncMock()
        client.action = AsyncMock(return_value={"h_commit": "a" * 64})
        result = await request_commit(runner, client, "g1", 1, "cop", {"step": 0})
        assert result == "a" * 64

    async def test_request_commit_no_h_commit(self):
        from agent.game_runner_turn import request_commit

        runner = self._make_runner()
        client = AsyncMock()
        client.action = AsyncMock(return_value={"ok": True})
        result = await request_commit(runner, client, "g1", 1, "cop", {"step": 0})
        assert result is None

    async def test_request_commit_exception(self):
        from agent.game_runner_turn import request_commit

        runner = self._make_runner()
        client = AsyncMock()
        client.action = AsyncMock(side_effect=Exception("network error"))
        result = await request_commit(runner, client, "g1", 1, "cop", {"step": 0})
        assert result is None

    async def test_request_reveal_success(self):
        from agent.game_runner_turn import request_reveal

        runner = self._make_runner()
        client = AsyncMock()
        client.action = AsyncMock(return_value={"move": "N", "h_commit": "a" * 64})
        result = await request_reveal(runner, client, "g1", 1, "cop")
        assert result["move"] == "N"

    async def test_request_reveal_no_move(self):
        from agent.game_runner_turn import request_reveal

        runner = self._make_runner()
        client = AsyncMock()
        client.action = AsyncMock(return_value={"ok": True})
        result = await request_reveal(runner, client, "g1", 1, "cop")
        assert result is None

    async def test_request_reveal_exception(self):
        from agent.game_runner_turn import request_reveal

        runner = self._make_runner()
        client = AsyncMock()
        client.action = AsyncMock(side_effect=Exception("timeout"))
        result = await request_reveal(runner, client, "g1", 1, "cop")
        assert result is None

    async def test_run_single_turn_commit_fails(self):
        from agent.game_runner_turn import _run_single_turn

        runner = self._make_runner()
        runner.cop_client = AsyncMock()
        runner.thief_client = AsyncMock()
        runner._board_to_state = MagicMock(return_value={"step": 0})

        board = MagicMock()
        rules = MagicMock()
        rules.get_scent_field = MagicMock(return_value=[])

        with patch("agent.game_runner_turn.request_commit", return_value=None):
            result = await _run_single_turn(runner, "g1", 1, board, rules)
        assert result == (None, "Commit failed at step 1")

    async def test_run_single_turn_reveal_fails(self):
        from agent.game_runner_turn import _run_single_turn

        runner = self._make_runner()
        runner.cop_client = AsyncMock()
        runner.thief_client = AsyncMock()
        runner._board_to_state = MagicMock(return_value={"step": 0})

        board = MagicMock()
        rules = MagicMock()
        rules.get_scent_field = MagicMock(return_value=[])

        with (
            patch("agent.game_runner_turn.request_commit", return_value="h" * 64),
            patch("agent.game_runner_turn.request_reveal", return_value=None),
        ):
            result = await _run_single_turn(runner, "g1", 1, board, rules)
        assert result == (None, "Reveal failed at step 1")

    async def test_run_single_turn_game_over(self):
        from agent.game_runner_turn import _run_single_turn
        from agent.rules_engine import GameOutcome

        runner = self._make_runner()
        runner.cop_client = AsyncMock()
        runner.thief_client = AsyncMock()
        runner._board_to_state = MagicMock(return_value={"step": 0})

        board = MagicMock()
        board.cop_position = [3, 3]
        board.thief_position = [3, 3]
        rules = MagicMock()
        rules.get_scent_field = MagicMock(return_value=[])
        rules.validate_move = MagicMock(return_value=True)
        rules.apply_moves = MagicMock()
        rules.check_game_status = MagicMock(return_value=GameOutcome.COP_WIN)

        with (
            patch("agent.game_runner_turn.request_commit", return_value="h" * 64),
            patch(
                "agent.game_runner_turn.request_reveal",
                return_value={"move": "N", "h_commit": "h" * 64},
            ),
        ):
            winner, abort = await _run_single_turn(runner, "g1", 1, board, rules)
        assert winner == "cop"
        assert abort is None

    async def test_run_single_turn_ongoing(self):
        from agent.game_runner_turn import _run_single_turn
        from agent.rules_engine import GameOutcome

        runner = self._make_runner()
        runner.cop_client = AsyncMock()
        runner.thief_client = AsyncMock()
        runner._board_to_state = MagicMock(return_value={"step": 0})

        board = MagicMock()
        board.cop_position = [0, 0]
        board.thief_position = [3, 3]
        rules = MagicMock()
        rules.get_scent_field = MagicMock(return_value=[])
        rules.validate_move = MagicMock(return_value=True)
        rules.apply_moves = MagicMock()
        rules.check_game_status = MagicMock(return_value=GameOutcome.ONGOING)

        with (
            patch("agent.game_runner_turn.request_commit", return_value="h" * 64),
            patch(
                "agent.game_runner_turn.request_reveal",
                return_value={"move": "S", "h_commit": "h" * 64},
            ),
        ):
            winner, abort = await _run_single_turn(runner, "g1", 1, board, rules)
        assert winner is None
        assert abort is None

    async def test_run_turn_loop_immediate_abort(self):
        from agent.game_runner_turn import run_turn_loop

        runner = self._make_runner()
        board = MagicMock()
        rules = MagicMock()

        with patch(
            "agent.game_runner_turn._run_single_turn", return_value=(None, "abort!")
        ):
            winner, abort, step = await run_turn_loop(
                runner, "g1", board, rules, max_turns=3, watchdog_timeout=60
            )
        assert abort == "abort!"

    async def test_run_turn_loop_winner(self):
        from agent.game_runner_turn import run_turn_loop

        runner = self._make_runner()
        board = MagicMock()
        rules = MagicMock()

        with patch(
            "agent.game_runner_turn._run_single_turn", return_value=("thief", None)
        ):
            winner, abort, step = await run_turn_loop(
                runner, "g1", board, rules, max_turns=5, watchdog_timeout=60
            )
        assert winner == "thief"
        assert abort is None

    async def test_run_turn_loop_none_outcome(self):
        """_run_single_turn returning None (not a tuple) triggers abort."""
        from agent.game_runner_turn import run_turn_loop

        runner = self._make_runner()
        board = MagicMock()
        rules = MagicMock()

        with patch("agent.game_runner_turn._run_single_turn", return_value=None):
            winner, abort, step = await run_turn_loop(
                runner, "g1", board, rules, max_turns=2, watchdog_timeout=60
            )
        assert abort is not None


# ===========================================================================
# agent/game_runner_audit.py
# ===========================================================================


class TestGameRunnerAudit:
    def _make_runner(self):
        runner = MagicMock()
        runner.config_sha256 = _SHA
        runner._log_event = MagicMock()
        runner._cop_commits = {1: "h" * 64}
        runner._thief_commits = {1: "h" * 64}
        runner._cop_reveals = {
            1: {"move": "N", "state_hash": "s" * 64, "hint": "", "intent": "truth"}
        }
        runner._thief_reveals = {
            1: {"move": "S", "state_hash": "s" * 64, "hint": "", "intent": "truth"}
        }
        return runner

    async def test_request_nonces_success(self):
        from agent.game_runner_audit import request_nonces

        runner = self._make_runner()
        client = AsyncMock()
        client.action = AsyncMock(return_value={"nonces": {"1": "nonce1"}})
        result = await request_nonces(runner, client, "g1", 1, "cop")
        assert result == {"1": "nonce1"}

    async def test_request_nonces_exception(self):
        from agent.game_runner_audit import request_nonces

        runner = self._make_runner()
        client = AsyncMock()
        client.action = AsyncMock(side_effect=Exception("timeout"))
        result = await request_nonces(runner, client, "g1", 1, "cop")
        assert result is None

    async def test_final_audit_missing_nonces(self):
        from agent.game_runner_audit import final_audit

        runner = self._make_runner()
        runner.cop_client = AsyncMock()
        runner.thief_client = AsyncMock()

        with patch("agent.game_runner_audit.request_nonces", return_value=None):
            ok, details = await final_audit(runner, "g1", 1)
        # Missing nonces means failed verification
        assert not ok or "cop_step_1" in details

    async def test_final_audit_passes(self):
        from agent.game_runner_audit import final_audit

        runner = self._make_runner()
        runner.cop_client = AsyncMock()
        runner.thief_client = AsyncMock()

        with (
            patch("agent.game_runner_audit.request_nonces", return_value={"1": "nonce1"}),
            patch("agent.game_runner_audit.verify_commitment", return_value=True),
        ):
            ok, details = await final_audit(runner, "g1", 1)
        assert ok
        assert details.get("cop_step_1") == "ok"
        assert details.get("thief_step_1") == "ok"

    async def test_final_audit_fails(self):
        from agent.game_runner_audit import final_audit

        runner = self._make_runner()
        runner.cop_client = AsyncMock()
        runner.thief_client = AsyncMock()

        with (
            patch("agent.game_runner_audit.request_nonces", return_value={"1": "nonce1"}),
            patch("agent.game_runner_audit.verify_commitment", return_value=False),
        ):
            ok, details = await final_audit(runner, "g1", 1)
        assert not ok

    async def test_request_nonces_empty(self):
        from agent.game_runner_audit import request_nonces

        runner = self._make_runner()
        client = AsyncMock()
        client.action = AsyncMock(return_value={"nonces": {}})
        result = await request_nonces(runner, client, "g1", 1, "thief")
        assert result == {}


# ===========================================================================
# agent/game_runner_reports.py
# ===========================================================================


class TestGameRunnerReports:
    def _make_report_mocks(self):
        """Return sys.modules patches for all heavy report dependencies."""
        mock_bundle = MagicMock()
        mock_manager = MagicMock()
        mock_factory = MagicMock()
        return {
            "agent.reports.bundle": mock_bundle,
            "agent.reports.manager": mock_manager,
            "agent.reports.plugin_factory": mock_factory,
        }, mock_bundle, mock_manager, mock_factory

    def _get_generate_reports(self):
        """Import generate_reports, breaking circular import by pre-mocking game_runner_output."""
        import importlib
        # Break the circular import: game_runner_reports -> game_runner_output -> game_runner_reports
        mock_output = MagicMock()
        mock_output.write_json = MagicMock()
        # Remove any stale cached modules to force a clean re-import
        for key in list(sys.modules.keys()):
            if "game_runner_reports" in key or "game_runner_output" in key:
                del sys.modules[key]
        with patch.dict("sys.modules", {"agent.game_runner_output": mock_output}):
            import agent.game_runner_reports as grr
        return grr.generate_reports, mock_output.write_json

    async def test_generate_reports_no_plugins(self, tmp_path):
        generate_reports, _ = self._get_generate_reports()

        runner = MagicMock()
        runner._game_dir = tmp_path
        runner.config_sha256 = _SHA

        mock_context = MagicMock()
        mock_builder_instance = AsyncMock()
        mock_builder_instance.build = AsyncMock(return_value=mock_context)
        mock_builder_cls = MagicMock(return_value=mock_builder_instance)

        mock_factory_cls = MagicMock()
        mock_factory_cls.from_config = AsyncMock(return_value=[])

        mock_reports_bundle = MagicMock()
        mock_reports_bundle.ReportBundleBuilder = mock_builder_cls
        mock_reports_plugin_factory = MagicMock()
        mock_reports_plugin_factory.ReportPluginFactory = mock_factory_cls

        with patch.dict("sys.modules", {
            "agent.reports.bundle": mock_reports_bundle,
            "agent.reports.plugin_factory": mock_reports_plugin_factory,
            "agent.reports.manager": MagicMock(),
            "tomllib": MagicMock(),
        }):
            await generate_reports(runner, "g1", {"winner": "cop", "final_step": 5})

    async def test_generate_reports_with_plugins(self, tmp_path):
        generate_reports, mock_write_json = self._get_generate_reports()

        runner = MagicMock()
        runner._game_dir = tmp_path
        runner.config_sha256 = _SHA

        mock_context = MagicMock()
        mock_builder_instance = AsyncMock()
        mock_builder_instance.build = AsyncMock(return_value=mock_context)
        mock_builder_cls = MagicMock(return_value=mock_builder_instance)

        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.status = "sent"
        mock_result.destination = "/tmp/report.txt"
        mock_result.error = None

        mock_manager_instance = MagicMock()
        mock_manager_instance.generate_all = AsyncMock(return_value={"file": mock_result})
        mock_manager_cls = MagicMock(return_value=mock_manager_instance)

        mock_factory_cls = MagicMock()
        mock_factory_cls.from_config = AsyncMock(return_value=[MagicMock()])

        mock_reports_bundle = MagicMock()
        mock_reports_bundle.ReportBundleBuilder = mock_builder_cls
        mock_reports_manager = MagicMock()
        mock_reports_manager.ReportManager = mock_manager_cls
        mock_reports_plugin_factory = MagicMock()
        mock_reports_plugin_factory.ReportPluginFactory = mock_factory_cls

        with patch.dict("sys.modules", {
            "agent.reports.bundle": mock_reports_bundle,
            "agent.reports.manager": mock_reports_manager,
            "agent.reports.plugin_factory": mock_reports_plugin_factory,
            "tomllib": MagicMock(),
        }):
            await generate_reports(runner, "g1", {"winner": "cop", "final_step": 3})

    async def test_generate_reports_failed_plugin(self, tmp_path):
        generate_reports, _ = self._get_generate_reports()

        runner = MagicMock()
        runner._game_dir = tmp_path
        runner.config_sha256 = _SHA

        mock_context = MagicMock()
        mock_builder_instance = AsyncMock()
        mock_builder_instance.build = AsyncMock(return_value=mock_context)
        mock_builder_cls = MagicMock(return_value=mock_builder_instance)

        mock_result = MagicMock()
        mock_result.ok = False
        mock_result.status = "failed"
        mock_result.destination = None
        mock_result.error = "smtp error"

        mock_manager_instance = MagicMock()
        mock_manager_instance.generate_all = AsyncMock(return_value={"email": mock_result})
        mock_manager_cls = MagicMock(return_value=mock_manager_instance)

        mock_factory_cls = MagicMock()
        mock_factory_cls.from_config = AsyncMock(return_value=[MagicMock()])

        mock_reports_bundle = MagicMock()
        mock_reports_bundle.ReportBundleBuilder = mock_builder_cls
        mock_reports_manager = MagicMock()
        mock_reports_manager.ReportManager = mock_manager_cls
        mock_reports_plugin_factory = MagicMock()
        mock_reports_plugin_factory.ReportPluginFactory = mock_factory_cls

        with patch.dict("sys.modules", {
            "agent.reports.bundle": mock_reports_bundle,
            "agent.reports.manager": mock_reports_manager,
            "agent.reports.plugin_factory": mock_reports_plugin_factory,
            "tomllib": MagicMock(),
        }):
            await generate_reports(runner, "g1", {"winner": "thief", "final_step": 10})

    async def test_generate_reports_exception_handled(self, tmp_path):
        generate_reports, _ = self._get_generate_reports()

        runner = MagicMock()
        runner._game_dir = tmp_path
        runner.config_sha256 = _SHA

        # Make reports bundle import fail inside the try block
        with patch.dict("sys.modules", {"agent.reports.bundle": None}):
            # Should not raise; logs the error
            await generate_reports(runner, "g1", {"winner": "cop"})
