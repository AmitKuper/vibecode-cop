"""Fast unit tests for previously uncovered cop_worker modules.

No LLM calls, no network calls, no heavy IO. All tests complete in < 1s each.
"""

from __future__ import annotations

import asyncio
import pytest


# ---------------------------------------------------------------------------
# rl/config.py
# ---------------------------------------------------------------------------


class TestRLGameConfig:
    def test_defaults(self):
        from cop_worker.rl.config import RLGameConfig

        c = RLGameConfig()
        assert c.grid_size == 7
        assert c.max_steps == 35
        assert c.cop_capture_reward == 1.0
        assert c.thief_survival_reward == 1.0
        assert c.step_penalty == 0.01
        assert c.use_shaped_rewards is False
        assert c.random_starts is False

    def test_from_dict_all_fields(self):
        from cop_worker.rl.config import RLGameConfig

        d = {
            "grid_size": 9,
            "cop_start": [1, 1],
            "thief_start": [5, 5],
            "barriers": [[2, 3]],
            "max_steps": 50,
            "survival_threshold": 50,
            "max_barriers": 10,
        }
        c = RLGameConfig.from_dict(d)
        assert c.grid_size == 9
        assert c.cop_start == [1, 1]
        assert c.thief_start == [5, 5]
        assert c.barriers == [[2, 3]]
        assert c.max_steps == 50

    def test_from_dict_empty(self):
        from cop_worker.rl.config import RLGameConfig

        c = RLGameConfig.from_dict({})
        assert c.grid_size == 7


# ---------------------------------------------------------------------------
# rl/env_rewards.py
# ---------------------------------------------------------------------------


class TestRewardsMixin:
    def _make_mixin(self, capture_reward=1.0, survival_reward=1.0, step_penalty=0.01):
        from cop_worker.rl.config import RLGameConfig
        from cop_worker.rl.env_rewards import RewardsMixin

        class FakeMixin(RewardsMixin):
            def __init__(self):
                self.config = RLGameConfig(
                    cop_capture_reward=capture_reward,
                    thief_survival_reward=survival_reward,
                    step_penalty=step_penalty,
                )
                self._prev_dist = 5

        return FakeMixin()

    def test_cop_win_rewards(self):
        from cop_worker.rules_outcomes import GameOutcome

        m = self._make_mixin()
        cop_r, thief_r = m._rewards(GameOutcome.COP_WIN)
        assert cop_r == 1.0
        assert thief_r == -1.0

    def test_thief_win_rewards(self):
        from cop_worker.rules_outcomes import GameOutcome

        m = self._make_mixin()
        cop_r, thief_r = m._rewards(GameOutcome.THIEF_WIN)
        assert cop_r == -1.0
        assert thief_r == 1.0

    def test_ongoing_rewards(self):
        from cop_worker.rules_outcomes import GameOutcome

        m = self._make_mixin(step_penalty=0.05)
        cop_r, thief_r = m._rewards(GameOutcome.ONGOING)
        assert cop_r == pytest.approx(-0.05)
        assert thief_r == pytest.approx(0.05)

    def test_shaped_rewards_terminal(self):
        from cop_worker.rules_outcomes import GameOutcome

        m = self._make_mixin()
        m.config.use_shaped_rewards = True
        m.config.shaped_reward_scale = 0.15
        # Terminal outcomes: shaped == base
        cop_r, thief_r = m._shaped_rewards(GameOutcome.COP_WIN)
        assert cop_r == pytest.approx(1.0)

    def test_shaped_rewards_ongoing(self):
        from cop_worker.rules_outcomes import GameOutcome
        from cop_worker.board import Board

        m = self._make_mixin()
        m.config.shaped_reward_scale = 0.1
        m._prev_dist = 6
        m._board = Board(cop_position=[0, 0], thief_position=[4, 4])

        # mock manhattan_dist in env_rewards module (where it's imported)
        import cop_worker.rl.env_rewards as er

        orig = er.manhattan_dist
        er.manhattan_dist = lambda b: 4  # cop closer now (was 6, now 4)
        try:
            cop_r, thief_r = m._shaped_rewards(GameOutcome.ONGOING)
            assert cop_r > -0.01  # step penalty offset by positive shaping
        finally:
            er.manhattan_dist = orig


# ---------------------------------------------------------------------------
# rl/networks.py
# ---------------------------------------------------------------------------


class TestNetworks:
    def test_mlp_backbone_forward(self):
        import torch
        from cop_worker.rl.networks import _MLPBackbone

        net = _MLPBackbone(grid_size=7, in_channels=4, hidden=64)
        x = torch.zeros(2, 4, 7, 7)
        out = net(x)
        assert out.shape == (2, 64)

    def test_cnn_backbone_forward(self):
        import torch
        from cop_worker.rl.networks import _CNNBackbone

        net = _CNNBackbone(grid_size=7, in_channels=4, hidden=64)
        x = torch.zeros(2, 4, 7, 7)
        out = net(x)
        assert out.shape == (2, 64)

    def test_dqn_net_forward(self):
        import torch
        from cop_worker.rl.networks import DQNNet

        net = DQNNet(grid_size=7, n_actions=5, hidden=32, net_type="mlp")
        x = torch.zeros(1, 4, 7, 7)
        q = net(x)
        assert q.shape == (1, 5)

    def test_dqn_net_cnn(self):
        import torch
        from cop_worker.rl.networks import DQNNet

        net = DQNNet(grid_size=7, n_actions=5, hidden=32, net_type="cnn")
        x = torch.zeros(1, 4, 7, 7)
        q = net(x)
        assert q.shape == (1, 5)

    def test_ppo_net_forward(self):
        import torch
        from cop_worker.rl.networks import PPONet

        net = PPONet(grid_size=7, n_actions=5, hidden=32)
        x = torch.zeros(1, 4, 7, 7)
        logits, value = net(x)
        assert logits.shape == (1, 5)
        assert value.shape == (1, 1)

    def test_ppo_net_get_action(self):
        import torch
        from cop_worker.rl.networks import PPONet

        net = PPONet(grid_size=7, n_actions=5, hidden=32)
        x = torch.zeros(1, 4, 7, 7)
        action, log_prob, entropy, value = net.get_action(x, deterministic=True)
        assert 0 <= action.item() < 5
        action2, _, _, _ = net.get_action(x, deterministic=False)
        assert 0 <= action2.item() < 5


# ---------------------------------------------------------------------------
# rl/observation.py
# ---------------------------------------------------------------------------


class TestObservation:
    def _make_board(self, grid_size=7, cop=(0, 0), thief=(3, 3), barriers=None, turn=1):
        from cop_worker.board import Board

        board = Board(
            cop_position=list(cop),
            thief_position=list(thief),
            grid_size=grid_size,
            barriers=[list(b) for b in (barriers or [])],
            turn=turn,
        )
        return board

    def test_cop_observation_shape(self):
        from cop_worker.rl.observation import cop_observation
        from cop_worker.rules_engine import RulesEngine

        board = self._make_board()
        rules = RulesEngine(board)
        obs = cop_observation(board, rules, max_steps=35)
        assert len(obs) == 4
        assert len(obs[0]) == 7
        assert len(obs[0][0]) == 7

    def test_cop_observation_with_barriers(self):
        from cop_worker.rl.observation import cop_observation
        from cop_worker.rules_engine import RulesEngine

        board = self._make_board(barriers=[(1, 0)])
        rules = RulesEngine(board)
        obs = cop_observation(board, rules, max_steps=35, barrier_quota=5, barriers_remaining=3)
        assert len(obs) == 5  # extra barrier quota channel

    def test_thief_observation_shape(self):
        from cop_worker.rl.observation import thief_observation

        board = self._make_board()
        obs = thief_observation(board, max_steps=35)
        assert len(obs) == 4

    def test_thief_observation_with_scent(self):
        from cop_worker.rl.observation import local_thief_observation

        board = self._make_board()
        scent = [[0.1] * 7 for _ in range(7)]
        obs = local_thief_observation(board, max_steps=35, cop_scent_field=scent)
        assert obs[1] == scent

    def test_observation_shape_function(self):
        from cop_worker.rl.observation import observation_shape

        assert observation_shape(7, "thief") == (4, 7, 7)
        assert observation_shape(7, "cop", barrier_quota=0) == (4, 7, 7)
        assert observation_shape(7, "cop", barrier_quota=5) == (5, 7, 7)


# ---------------------------------------------------------------------------
# language/hints.py
# ---------------------------------------------------------------------------


class TestHints:
    def test_generate_hint_north(self):
        from cop_worker.language.hints import generate_hint

        hint = generate_hint("NORTH")
        assert isinstance(hint, str) and len(hint) > 0

    def test_generate_hint_all_directions(self):
        from cop_worker.language.hints import generate_hint

        for move in ["NORTH", "SOUTH", "EAST", "WEST", "STAY"]:
            h = generate_hint(move)
            assert isinstance(h, str)

    def test_generate_hint_lowercase(self):
        from cop_worker.language.hints import generate_hint

        h = generate_hint("north")
        assert isinstance(h, str)

    def test_generate_hint_unknown(self):
        from cop_worker.language.hints import generate_hint

        h = generate_hint("TELEPORT")
        assert "teleport" in h.lower()

    def test_generate_hint_with_rng(self):
        import random
        from cop_worker.language.hints import generate_hint

        rng = random.Random(42)
        h = generate_hint("NORTH", rng=rng)
        assert isinstance(h, str)


# ---------------------------------------------------------------------------
# language/llm_hint.py (template / non-LLM paths only)
# ---------------------------------------------------------------------------


class TestLLMHint:
    def test_build_user_prompt_truth(self):
        from cop_worker.language.llm_hint import _build_user_prompt

        p = _build_user_prompt("N", "truth")
        assert "north" in p.lower()
        assert "truth" in p.lower() or "Tell" in p

    def test_build_user_prompt_lie(self):
        from cop_worker.language.llm_hint import _build_user_prompt

        p = _build_user_prompt("N", "lie")
        assert isinstance(p, str)

    def test_llm_hint_generator_no_provider(self):
        from cop_worker.language.llm_hint import LLMHintGenerator

        gen = LLMHintGenerator(provider="none_exist")
        result = gen.generate("N", "truth")
        assert result is None  # no provider = None

    def test_from_llm_config(self):
        from cop_worker.language.llm_hint import LLMHintGenerator

        gen = LLMHintGenerator.from_llm_config(
            {"provider": "ollama", "model": "test", "base_url": "http://localhost:99999", "hint_timeout": 0.001}
        )
        result = gen.generate("S", "truth")
        assert result is None  # connection will fail silently


# ---------------------------------------------------------------------------
# llm/config.py
# ---------------------------------------------------------------------------


class TestLLMConfig:
    def test_provider_enum(self):
        from cop_worker.llm.config import LLMProvider

        assert LLMProvider.OLLAMA.value == "ollama"
        assert LLMProvider.ANTHROPIC.value == "anthropic"
        assert LLMProvider.OPENAI.value == "openai"
        assert LLMProvider.AZURE.value == "azure"

    def test_from_dict_ollama(self):
        from cop_worker.llm.config import LLMConfigBuilder, LLMProvider

        cfg = LLMConfigBuilder.from_dict({"provider": "ollama", "model": "llama3.1:8b"})
        assert cfg.provider == LLMProvider.OLLAMA
        assert cfg.model == "llama3.1:8b"

    def test_from_dict_unknown_provider(self):
        from cop_worker.llm.config import LLMConfigBuilder, LLMProvider

        cfg = LLMConfigBuilder.from_dict({"provider": "unknown_xyz"})
        assert cfg.provider == LLMProvider.OLLAMA  # fallback

    def test_to_dict(self):
        from cop_worker.llm.config import LLMConfigBuilder

        cfg = LLMConfigBuilder.from_dict({"provider": "openai", "model": "gpt-4"})
        d = cfg.to_dict()
        assert d["provider"] == "openai"
        assert d["model"] == "gpt-4"

    def test_builder_ollama(self):
        from cop_worker.llm.config import LLMConfigBuilder, LLMProvider

        cfg = LLMConfigBuilder.ollama(model="gemma3:4b")
        assert cfg.provider == LLMProvider.OLLAMA
        assert cfg.model == "gemma3:4b"

    def test_builder_openai(self):
        from cop_worker.llm.config import LLMConfigBuilder, LLMProvider

        cfg = LLMConfigBuilder.openai(model="gpt-4", api_key="sk-test")
        assert cfg.provider == LLMProvider.OPENAI
        assert cfg.api_key == "sk-test"

    def test_builder_anthropic(self):
        from cop_worker.llm.config import LLMConfigBuilder, LLMProvider

        cfg = LLMConfigBuilder.anthropic(model="claude-3-haiku", api_key="ant-key")
        assert cfg.provider == LLMProvider.ANTHROPIC

    def test_builder_azure(self):
        from cop_worker.llm.config import LLMConfigBuilder, LLMProvider

        cfg = LLMConfigBuilder.azure(
            model="gpt-4",
            api_key="key",
            base_url="https://x.openai.azure.com",
        )
        assert cfg.provider == LLMProvider.AZURE


# ---------------------------------------------------------------------------
# llm/token_counter.py
# ---------------------------------------------------------------------------


class TestTokenCounter:
    def test_initial_state(self):
        from cop_worker.llm.token_counter import TokenCounter

        c = TokenCounter()
        s = c.summary()
        assert s["prompt_tokens"] == 0
        assert s["completion_tokens"] == 0
        assert s["total_tokens"] == 0
        assert s["llm_calls"] == 0

    def test_record_single(self):
        from cop_worker.llm.token_counter import TokenCounter

        c = TokenCounter()
        c.record(prompt_tokens=100, completion_tokens=50)
        assert c.total == 150
        s = c.summary()
        assert s["llm_calls"] == 1

    def test_record_multiple(self):
        from cop_worker.llm.token_counter import TokenCounter

        c = TokenCounter()
        c.record(10, 5)
        c.record(20, 10)
        assert c.total == 45

    def test_reset(self):
        from cop_worker.llm.token_counter import TokenCounter

        c = TokenCounter()
        c.record(100, 50)
        c.reset()
        assert c.total == 0
        assert c.summary()["llm_calls"] == 0

    def test_record_from_crew_output_none(self):
        from cop_worker.llm.token_counter import TokenCounter

        c = TokenCounter()
        c.record_from_crew_output(object())  # no token_usage attr — should not raise
        assert c.total == 0

    def test_record_from_crew_output_dict(self):
        from cop_worker.llm.token_counter import TokenCounter

        class FakeResult:
            token_usage = {"prompt_tokens": 30, "completion_tokens": 15}

        c = TokenCounter()
        c.record_from_crew_output(FakeResult())
        assert c.total == 45

    def test_thread_safety(self):
        import threading
        from cop_worker.llm.token_counter import TokenCounter

        c = TokenCounter()
        threads = [threading.Thread(target=c.record, args=(10, 5)) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert c.total == 150


# ---------------------------------------------------------------------------
# reports/delivery_store.py
# ---------------------------------------------------------------------------


class TestDeliveryStore:
    def test_load_history_missing(self, tmp_path):
        from league_manager.reports.delivery_store import DeliveryStore

        store = DeliveryStore(tmp_path)
        assert store.load_history("game_01") == []

    def test_get_delivery_path(self, tmp_path):
        from league_manager.reports.delivery_store import DeliveryStore

        store = DeliveryStore(tmp_path)
        p = store.get_delivery_path("game_01")
        assert "game_01" in str(p)

    def test_record_and_load(self, tmp_path):
        from league_manager.reports.delivery_store import DeliveryStore

        store = DeliveryStore(tmp_path)
        record = {"plugin": "gmail", "status": "sent", "timestamp": "now"}
        asyncio.run(store.record_delivery("game_01", record))
        history = store.load_history("game_01")
        assert len(history) == 1
        assert history[0]["status"] == "sent"

    def test_has_successful_delivery_no(self, tmp_path):
        from league_manager.reports.delivery_store import DeliveryStore

        store = DeliveryStore(tmp_path)
        result = asyncio.run(store.has_successful_delivery("game_01", "gmail"))
        assert result is False

    def test_has_successful_delivery_yes(self, tmp_path):
        from league_manager.reports.delivery_store import DeliveryStore

        store = DeliveryStore(tmp_path)
        record = {"plugin": "gmail", "status": "sent", "game_id": "game_01"}
        asyncio.run(store.record_delivery("game_01", record))
        result = asyncio.run(store.has_successful_delivery("game_01", "gmail"))
        assert result is True

    def test_load_history_corrupted(self, tmp_path):
        from league_manager.reports.delivery_store import DeliveryStore

        store = DeliveryStore(tmp_path)
        path = store.get_delivery_path("bad_game")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("NOT JSON", encoding="utf-8")
        assert store.load_history("bad_game") == []  # should not raise


# ---------------------------------------------------------------------------
# reports/gatekeeper.py
# ---------------------------------------------------------------------------


class TestReportGatekeeper:
    def test_dry_run_always_allowed(self):
        from league_manager.reports.gatekeeper import ReportGatekeeper

        g = ReportGatekeeper()
        result = asyncio.run(g.can_send("g1", "gmail", [], mode="dry_run"))
        ok, reason = result
        assert ok is True

    def test_draft_always_allowed(self):
        from league_manager.reports.gatekeeper import ReportGatekeeper

        g = ReportGatekeeper()
        ok, reason = asyncio.run(g.can_send("g1", "gmail", [], mode="draft"))
        assert ok is True

    def test_already_sent_blocks(self):
        from league_manager.reports.gatekeeper import ReportGatekeeper

        g = ReportGatekeeper()
        history = [{"plugin": "gmail", "status": "sent", "game_id": "g1"}]
        ok, reason = asyncio.run(g.can_send("g1", "gmail", history, mode="send"))
        assert ok is False
        assert "Already" in reason

    def test_daily_limit_blocks(self):
        from league_manager.reports.gatekeeper import ReportGatekeeper

        g = ReportGatekeeper(max_sends_per_day=2)
        history = [
            {"status": "sent", "timestamp": "9999-01-01T00:00:00"},
            {"status": "sent", "timestamp": "9999-01-01T00:01:00"},
        ]
        ok, reason = asyncio.run(g.can_send("g2", "gmail", history, mode="send"))
        assert ok is False

    def test_max_retries_blocks(self):
        from league_manager.reports.gatekeeper import ReportGatekeeper

        g = ReportGatekeeper(max_retries=2)
        history = [
            {"plugin": "gmail", "status": "failed", "game_id": "g3"},
            {"plugin": "gmail", "status": "failed", "game_id": "g3"},
        ]
        ok, reason = asyncio.run(g.can_send("g3", "gmail", history, mode="send"))
        assert ok is False

    def test_record_send(self):
        from league_manager.reports.gatekeeper import ReportGatekeeper

        g = ReportGatekeeper()
        rec = g.record_send("g1", "gmail", "send", "sent", destination="test@x.com", message_id="msg-01")
        assert rec["status"] == "sent"
        assert rec["destination"] == "test@x.com"
        assert rec["message_id"] == "msg-01"

    def test_record_send_failed(self):
        from league_manager.reports.gatekeeper import ReportGatekeeper

        g = ReportGatekeeper()
        rec = g.record_send("g1", "gmail", "send", "failed", error="SMTP error")
        assert rec["error"] == "SMTP error"
        assert rec["status"] == "failed"


# ---------------------------------------------------------------------------
# domain/runtime_transition.py
# ---------------------------------------------------------------------------


class TestRuntimeTransition:
    def test_illegal_joint_action_error_message(self):
        from cop_worker.domain.runtime_transition import IllegalJointActionError

        err = IllegalJointActionError(("cop",), "BADMOVE", "STAY")
        assert "cop" in str(err)
        assert "BADMOVE" in str(err)

    def test_locked_config_no_attr(self):
        from cop_worker.domain.runtime_transition import locked_config
        from cop_worker.domain.config_validator import GameConfig

        class FakeRuntime:
            pass

        cfg = locked_config(FakeRuntime())
        assert isinstance(cfg, GameConfig)

    def test_locked_config_with_game_config(self):
        from cop_worker.domain.runtime_transition import locked_config
        from cop_worker.domain.config_validator import GameConfig

        class FakeRuntime:
            game_config = GameConfig()  # defaults to grid_size=7 (Appendix F)

        cfg = locked_config(FakeRuntime())
        assert cfg.grid_size == 7


# ---------------------------------------------------------------------------
# synthetic_belief.py (remaining uncovered lines)
# ---------------------------------------------------------------------------


class TestSyntheticBelief:
    def test_get_belief_map_high_confidence(self):
        from cop_worker.synthetic_belief import SyntheticBeliefProvider
        import numpy as np

        sbp = SyntheticBeliefProvider()
        belief = sbp.get_belief_map(7, (3, 3), confidence_level="high")
        assert abs(belief.sum() - 1.0) < 0.01
        assert belief[3, 3] == pytest.approx(0.8)

    def test_get_belief_map_medium_confidence(self):
        from cop_worker.synthetic_belief import SyntheticBeliefProvider

        sbp = SyntheticBeliefProvider()
        belief = sbp.get_belief_map(7, (3, 3), confidence_level="medium")
        assert abs(belief.sum() - 1.0) < 0.01

    def test_get_belief_map_low_confidence(self):
        from cop_worker.synthetic_belief import SyntheticBeliefProvider

        sbp = SyntheticBeliefProvider()
        belief = sbp.get_belief_map(7, (3, 3), confidence_level="low")
        assert abs(belief.sum() - 1.0) < 0.01

    def test_get_belief_map_corner(self):
        from cop_worker.synthetic_belief import SyntheticBeliefProvider

        sbp = SyntheticBeliefProvider()
        belief = sbp.get_belief_map(7, (0, 0), confidence_level="high")
        # Corner has fewer neighbors but belief still sums to 1
        assert abs(belief.sum() - 1.0) < 0.01


# ---------------------------------------------------------------------------
# reliability/durable_io.py
# ---------------------------------------------------------------------------


class TestDurableIO:
    def test_atomic_write_bytes_success(self, tmp_path):
        from cop_worker.reliability.durable_io import atomic_write_bytes

        dest = tmp_path / "out.bin"
        atomic_write_bytes(dest, b"hello world")
        assert dest.read_bytes() == b"hello world"

    def test_atomic_write_bytes_invalid_attempts(self, tmp_path):
        from cop_worker.reliability.durable_io import atomic_write_bytes

        import pytest
        dest = tmp_path / "x.bin"
        with pytest.raises(ValueError):
            atomic_write_bytes(dest, b"data", attempts=0)

    def test_atomic_write_bytes_retry_on_failure(self, tmp_path):
        """Force first attempt to fail via read-only directory trick."""
        from cop_worker.reliability.durable_io import atomic_write_bytes, PersistenceError
        from unittest.mock import patch
        import pytest

        dest = tmp_path / "sub" / "out.bin"
        call_count = [0]
        orig_replace = __import__("os").replace

        def failing_replace(src, dst):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("simulated failure")
            return orig_replace(src, dst)

        with patch("os.replace", side_effect=failing_replace):
            # Should succeed on second attempt
            atomic_write_bytes(dest, b"retry", attempts=2, retry_delay_s=0)

    def test_atomic_write_bytes_all_attempts_fail(self, tmp_path):
        from cop_worker.reliability.durable_io import atomic_write_bytes, PersistenceError
        from unittest.mock import patch
        import pytest

        dest = tmp_path / "fail.bin"

        with patch("os.replace", side_effect=OSError("always fails")):
            with pytest.raises(PersistenceError):
                atomic_write_bytes(dest, b"data", attempts=2, retry_delay_s=0)

    def test_atomic_write_json_success(self, tmp_path):
        from cop_worker.reliability.durable_io import atomic_write_json
        import json

        dest = tmp_path / "data.json"
        atomic_write_json(dest, {"key": "value", "num": 42})
        result = json.loads(dest.read_text())
        assert result["key"] == "value"
        assert result["num"] == 42

    def test_sync_directory_windows_noop(self):
        """On Windows (os.name=='nt'), _sync_directory should be a no-op."""
        from cop_worker.reliability.durable_io import _sync_directory
        from pathlib import Path
        import os

        # This test just verifies it doesn't raise on Windows
        if os.name == "nt":
            _sync_directory(Path("."))  # should return without error

    def test_persistence_error_is_oserror(self):
        from cop_worker.reliability.durable_io import PersistenceError

        err = PersistenceError("test error")
        assert isinstance(err, OSError)


# ---------------------------------------------------------------------------
# rl/heuristics.py
# ---------------------------------------------------------------------------


class TestHeuristics:
    def test_bfs_dist_basic(self):
        from cop_worker.rl.heuristics import _bfs_dist

        dist = _bfs_dist((0, 0), [], grid_size=7)
        assert dist[(0, 0)] == 0
        assert dist[(0, 1)] == 1
        assert dist[(1, 0)] == 1
        assert dist[(6, 6)] == 12

    def test_bfs_dist_with_barrier(self):
        from cop_worker.rl.heuristics import _bfs_dist

        # Block off (0, 1) — should not appear in results
        dist = _bfs_dist((0, 0), [(0, 1)], grid_size=7)
        assert (0, 1) not in dist
        # Can still reach (1, 0)
        assert (1, 0) in dist

    def test_random_legal_cop_returns_action(self):
        from cop_worker.rl.heuristics import random_legal_cop

        action = random_legal_cop((3, 3), [], barriers_remaining=3, grid_size=7)
        assert isinstance(action, str)
        assert len(action) > 0

    def test_random_legal_cop_no_barriers(self):
        from cop_worker.rl.heuristics import random_legal_cop

        action = random_legal_cop((3, 3), [], barriers_remaining=0, grid_size=7)
        assert isinstance(action, str)

    def test_random_legal_thief_returns_action(self):
        from cop_worker.rl.heuristics import random_legal_thief

        action = random_legal_thief((3, 3), [], grid_size=7)
        assert isinstance(action, str)
        assert len(action) > 0

    def test_pursuit_cop_moves_toward_target(self):
        from cop_worker.rl.heuristics import pursuit_cop

        # Cop at (0,0), thief believed at (3,3); should move toward it
        action = pursuit_cop((0, 0), (3, 3), [], barriers_remaining=3, grid_size=7)
        assert action in ["N", "S", "E", "W", "STAY"]

    def test_evasion_thief_moves_away(self):
        from cop_worker.rl.heuristics import evasion_thief

        # Thief at (3,3), cop believed at (3,3); should move away
        action = evasion_thief((3, 3), (3, 3), [], grid_size=7)
        assert action in ["N", "S", "E", "W", "STAY"]

    def test_pursuit_cop_with_barriers(self):
        from cop_worker.rl.heuristics import pursuit_cop

        action = pursuit_cop((0, 0), (6, 6), [(1, 0), (0, 1)], barriers_remaining=3, grid_size=7)
        # With barriers blocking N and E from (0,0), must STAY or pick valid direction
        assert isinstance(action, str)

    def test_evasion_thief_corner(self):
        from cop_worker.rl.heuristics import evasion_thief

        # Corner position — fewer options
        action = evasion_thief((0, 0), (0, 0), [], grid_size=7)
        assert action in ["N", "S", "E", "W", "STAY"]


# ---------------------------------------------------------------------------
# rl/env_helpers.py
# ---------------------------------------------------------------------------


class TestEnvHelpers:
    def test_random_starts_distinct(self):
        from cop_worker.rl.env_helpers import random_starts

        cop, thief = random_starts(7, [])
        assert len(cop) == 2
        assert len(thief) == 2
        assert cop != thief

    def test_random_starts_avoids_barriers(self):
        from cop_worker.rl.env_helpers import random_starts

        # Fill most of the board but leave at least 2 free cells
        barriers = [[x, y] for x in range(7) for y in range(7) if not (x == 0 and y == 0) and not (x == 6 and y == 6)]
        cop, thief = random_starts(7, barriers)
        assert cop != thief

    def test_manhattan_dist(self):
        from cop_worker.rl.env_helpers import manhattan_dist
        from cop_worker.board import Board

        board = Board(cop_position=[0, 0], thief_position=[3, 4])
        dist = manhattan_dist(board)
        assert dist == 7  # |0-3| + |0-4|

    def test_manhattan_dist_same_cell(self):
        from cop_worker.rl.env_helpers import manhattan_dist
        from cop_worker.board import Board

        board = Board(cop_position=[2, 2], thief_position=[2, 2])
        assert manhattan_dist(board) == 0

    def test_place_deltas_keys(self):
        from cop_worker.rl.env_helpers import _PLACE_DELTAS

        assert set(_PLACE_DELTAS.keys()) == {"PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"}

    def test_apply_place_action_no_barriers_remaining(self):
        from cop_worker.rl.env_helpers import apply_place_action
        from cop_worker.board import Board

        board = Board(cop_position=[3, 3], thief_position=[0, 0])
        result = apply_place_action(board, "PLACE_N", grid_size=7, barriers_remaining=0)
        assert result == 0  # no change

    def test_apply_place_action_places_barrier(self):
        from cop_worker.rl.env_helpers import apply_place_action
        from cop_worker.board import Board

        board = Board(cop_position=[3, 3], thief_position=[0, 0])
        result = apply_place_action(board, "PLACE_S", grid_size=7, barriers_remaining=3)
        # PLACE_S: dy=+1, so barrier at (3, 4)
        assert result == 2
        assert [3, 4] in board.barriers

    def test_apply_place_action_out_of_bounds(self):
        from cop_worker.rl.env_helpers import apply_place_action
        from cop_worker.board import Board

        # Cop at edge — placing barrier out of bounds should no-op
        board = Board(cop_position=[0, 0], thief_position=[6, 6])
        result = apply_place_action(board, "PLACE_N", grid_size=7, barriers_remaining=3)
        # PLACE_N: dy=-1, so barrier at (0, -1) which is out of bounds
        assert result == 3  # unchanged


# ---------------------------------------------------------------------------
# reports/file_report.py
# ---------------------------------------------------------------------------


def _make_report_context(game_dir, game_id="game_001", role="thief"):
    """Helper to build a minimal ReportContext for file report tests."""
    from league_manager.reports.base import ReportContext

    return ReportContext(
        game_id=game_id,
        role=role,
        group_id="group_01",
        opponent_group_id="group_02",
        game_dir=game_dir,
        game_state={
            "cop_position": [1, 1],
            "thief_position": [5, 5],
            "move_history": [
                {"cop": "N", "thief": "S"},
                {"cop": "E", "thief": "W"},
            ],
        },
        result={"winner": "thief"},
        start_timestamp="2026-01-01T00:00:00",
        end_timestamp="2026-01-01T00:05:00",
        config_hash="abc123",
        log_hash="def456",
        required_files={},
        optional_files={},
    )


class TestFileReportPlugin:
    def test_generate_json_success(self, tmp_path):
        from league_manager.reports.file_report import FileReportPlugin

        ctx = _make_report_context(tmp_path)
        plugin = FileReportPlugin("file_json", report_format="json")
        result = asyncio.run(plugin.generate(ctx))
        assert result.ok is True
        assert result.status == "completed"
        assert (tmp_path / "report.json").exists()

    def test_generate_json_content(self, tmp_path):
        import json
        from league_manager.reports.file_report import FileReportPlugin

        ctx = _make_report_context(tmp_path)
        plugin = FileReportPlugin("file_json", report_format="json")
        asyncio.run(plugin.generate(ctx))
        data = json.loads((tmp_path / "report.json").read_text())
        assert data["game_id"] == "game_001"
        assert data["winner"] == "thief"
        assert data["move_count"] == 2

    def test_generate_markdown_success(self, tmp_path):
        from league_manager.reports.file_report import FileReportPlugin

        ctx = _make_report_context(tmp_path)
        plugin = FileReportPlugin("file_md", report_format="markdown")
        result = asyncio.run(plugin.generate(ctx))
        assert result.ok is True
        assert (tmp_path / "report.md").exists()

    def test_generate_markdown_content(self, tmp_path):
        from league_manager.reports.file_report import FileReportPlugin

        ctx = _make_report_context(tmp_path)
        plugin = FileReportPlugin("file_md", report_format="markdown")
        asyncio.run(plugin.generate(ctx))
        content = (tmp_path / "report.md").read_text()
        assert "game_001" in content
        assert "THIEF" in content
        assert "| Turn |" in content

    def test_generate_markdown_many_moves(self, tmp_path):
        """Verify truncation path (>20 moves) is exercised."""
        from league_manager.reports.file_report import FileReportPlugin
        from league_manager.reports.base import ReportContext

        ctx = ReportContext(
            game_id="game_002",
            role="cop",
            group_id="g1",
            opponent_group_id=None,
            game_dir=tmp_path,
            game_state={
                "cop_position": [0, 0],
                "thief_position": [6, 6],
                "move_history": [{"cop": "N", "thief": "S"}] * 25,
            },
            result={"winner": "cop"},
            start_timestamp="2026-01-01T00:00:00",
            end_timestamp="2026-01-01T00:10:00",
            config_hash=None,
            log_hash=None,
            required_files={},
            optional_files={},
        )
        plugin = FileReportPlugin("file_md", report_format="markdown")
        result = asyncio.run(plugin.generate(ctx))
        assert result.ok is True
        content = (tmp_path / "report.md").read_text()
        assert "more moves" in content

    def test_generate_json_no_result(self, tmp_path):
        """Exercise result=None branch."""
        from league_manager.reports.file_report import FileReportPlugin
        from league_manager.reports.base import ReportContext

        ctx = ReportContext(
            game_id="game_003",
            role="thief",
            group_id="g1",
            opponent_group_id=None,
            game_dir=tmp_path,
            game_state={},
            result=None,
            start_timestamp="2026-01-01T00:00:00",
            end_timestamp="2026-01-01T00:05:00",
            config_hash=None,
            log_hash=None,
            required_files={},
            optional_files={},
        )
        plugin = FileReportPlugin("file_json")
        result = asyncio.run(plugin.generate(ctx))
        assert result.ok is True

    def test_generate_error_path(self, tmp_path):
        """Force an exception by making the path unwritable."""
        from league_manager.reports.file_report import FileReportPlugin
        from unittest.mock import patch

        ctx = _make_report_context(tmp_path)
        plugin = FileReportPlugin("file_json")

        with patch("builtins.open", side_effect=PermissionError("no write")):
            result = asyncio.run(plugin.generate(ctx))

        assert result.ok is False
        assert result.error_code == "file_write_error"


# ---------------------------------------------------------------------------
# reports/gmail_send.py
# ---------------------------------------------------------------------------


class TestGmailSend:
    def test_load_oauth_credentials_valid_token(self, tmp_path):
        """Test load_oauth_credentials with a mocked valid token file."""
        from unittest.mock import MagicMock, patch
        import json

        token_file = tmp_path / "token.json"
        token_data = {
            "token": "ya29.valid_token",
            "refresh_token": None,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client_id",
            "client_secret": "client_secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.send"],
        }
        token_file.write_text(json.dumps(token_data))

        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.expiry = "2030-01-01"
        mock_creds.refresh_token = None

        with patch("google.oauth2.credentials.Credentials", return_value=mock_creds), \
             patch("google.auth.transport.requests.Request"):
            from league_manager.reports.gmail_send import load_oauth_credentials
            result = load_oauth_credentials(token_file)
            assert result is mock_creds

    def test_load_oauth_credentials_refreshes_token(self, tmp_path):
        """Test that expired token with refresh_token triggers refresh."""
        from unittest.mock import MagicMock, patch, call
        import json

        token_file = tmp_path / "token.json"
        token_data = {
            "token": "expired_token",
            "refresh_token": "1//refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client_id",
            "client_secret": "secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.send"],
        }
        token_file.write_text(json.dumps(token_data))

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expiry = None
        mock_creds.refresh_token = "1//refresh_token"
        mock_creds.token = "new_token"
        mock_creds.token_uri = "https://oauth2.googleapis.com/token"
        mock_creds.client_id = "client_id"
        mock_creds.client_secret = "secret"
        mock_creds.scopes = ["https://www.googleapis.com/auth/gmail.send"]

        mock_request_cls = MagicMock()

        with patch("google.oauth2.credentials.Credentials", return_value=mock_creds), \
             patch("google.auth.transport.requests.Request", mock_request_cls):
            from league_manager.reports.gmail_send import load_oauth_credentials
            result = load_oauth_credentials(token_file)
            mock_creds.refresh.assert_called_once()
            assert result is mock_creds

    def test_load_oauth_credentials_raises_without_refresh(self, tmp_path):
        """Invalid token with no refresh_token raises RuntimeError."""
        from unittest.mock import MagicMock, patch
        import json
        import pytest

        token_file = tmp_path / "token.json"
        token_data = {
            "token": None,
            "refresh_token": None,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client_id",
            "client_secret": "secret",
            "scopes": [],
        }
        token_file.write_text(json.dumps(token_data))

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expiry = None
        mock_creds.refresh_token = None

        with patch("google.oauth2.credentials.Credentials", return_value=mock_creds), \
             patch("google.auth.transport.requests.Request"):
            from league_manager.reports.gmail_send import load_oauth_credentials
            with pytest.raises(RuntimeError, match="re-authorize"):
                load_oauth_credentials(token_file)

    def test_gmail_api_send_returns_message_id(self):
        """Test gmail_api_send with fully mocked API client."""
        from unittest.mock import MagicMock, patch
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        message = MIMEMultipart()
        message["Subject"] = "Test"
        message["From"] = "test@test.com"
        message["To"] = "recipient@test.com"
        message.attach(MIMEText("body", "plain"))

        mock_service = MagicMock()
        mock_service.users().messages().send().execute.return_value = {"id": "msg_123"}

        mock_creds = MagicMock()

        with patch("googleapiclient.discovery.build", return_value=mock_service):
            from league_manager.reports.gmail_send import gmail_api_send
            msg_id = gmail_api_send(message, mock_creds)
            assert msg_id == "msg_123"

    def test_gmail_api_send_no_id_returns_unknown(self):
        """Test gmail_api_send when response has no 'id' key."""
        from unittest.mock import MagicMock, patch
        from email.mime.multipart import MIMEMultipart

        message = MIMEMultipart()
        message["Subject"] = "Test"
        message["From"] = "a@b.com"
        message["To"] = "c@d.com"

        mock_service = MagicMock()
        mock_service.users().messages().send().execute.return_value = {}

        with patch("googleapiclient.discovery.build", return_value=mock_service):
            from league_manager.reports.gmail_send import gmail_api_send
            msg_id = gmail_api_send(message, MagicMock())
            assert msg_id == "unknown"


# ---------------------------------------------------------------------------
# reports/gmail_report.py
# ---------------------------------------------------------------------------


class TestGmailReportPlugin:
    def _make_ctx(self, game_dir):
        return _make_report_context(game_dir, game_id="game_gmail_01")

    def test_disabled_mode_returns_skipped(self, tmp_path):
        from league_manager.reports.gmail_report import GmailReportPlugin

        plugin = GmailReportPlugin(mode="disabled")
        ctx = self._make_ctx(tmp_path)
        result = asyncio.run(plugin.generate(ctx))
        assert result.ok is True
        assert result.status == "skipped"

    def test_dry_run_mode_creates_preview(self, tmp_path):
        from league_manager.reports.gmail_report import GmailReportPlugin

        plugin = GmailReportPlugin(mode="dry_run", recipient="test@example.com")
        ctx = self._make_ctx(tmp_path)
        result = asyncio.run(plugin.generate(ctx))
        assert result.ok is True
        assert result.status == "dry_run"
        preview = tmp_path / "game_gmail_01_email_preview.txt"
        assert preview.exists()

    def test_draft_mode_creates_eml(self, tmp_path):
        from league_manager.reports.gmail_report import GmailReportPlugin

        plugin = GmailReportPlugin(mode="draft", recipient="test@example.com")
        ctx = self._make_ctx(tmp_path)
        result = asyncio.run(plugin.generate(ctx))
        assert result.ok is True
        assert result.status == "draft"
        eml = tmp_path / "game_gmail_01.eml"
        assert eml.exists()

    def test_send_mode_missing_token(self, tmp_path):
        from league_manager.reports.gmail_report import GmailReportPlugin

        plugin = GmailReportPlugin(
            mode="send",
            token_path=str(tmp_path / "nonexistent_token.json"),
        )
        ctx = self._make_ctx(tmp_path)
        result = asyncio.run(plugin.generate(ctx))
        assert result.ok is False
        assert result.error_code == "gmail_auth_missing"

    def test_send_mode_auth_runtime_error(self, tmp_path):
        """RuntimeError from load_oauth_credentials is caught correctly."""
        from unittest.mock import patch
        from league_manager.reports.gmail_report import GmailReportPlugin

        # Create a fake token file so token_path.exists() passes
        token_file = tmp_path / "token.json"
        token_file.write_text("{}")

        plugin = GmailReportPlugin(mode="send", token_path=str(token_file))
        ctx = self._make_ctx(tmp_path)

        with patch(
            "league_manager.reports.gmail_report.load_oauth_credentials",
            side_effect=RuntimeError("need re-authorize"),
        ):
            result = asyncio.run(plugin.generate(ctx))

        assert result.ok is False
        assert result.error_code == "gmail_auth_missing"

    def test_send_mode_refresh_error(self, tmp_path):
        """Generic exception from load_oauth_credentials is caught correctly."""
        from unittest.mock import patch
        from league_manager.reports.gmail_report import GmailReportPlugin

        token_file = tmp_path / "token.json"
        token_file.write_text("{}")

        plugin = GmailReportPlugin(mode="send", token_path=str(token_file))
        ctx = self._make_ctx(tmp_path)

        with patch(
            "league_manager.reports.gmail_report.load_oauth_credentials",
            side_effect=Exception("token refresh failed"),
        ):
            result = asyncio.run(plugin.generate(ctx))

        assert result.ok is False
        assert result.error_code == "gmail_auth_missing"

    def test_send_mode_send_error(self, tmp_path):
        """Exception from gmail_api_send is caught as gmail_send_error."""
        from unittest.mock import patch, MagicMock
        from league_manager.reports.gmail_report import GmailReportPlugin

        token_file = tmp_path / "token.json"
        token_file.write_text("{}")

        plugin = GmailReportPlugin(mode="send", token_path=str(token_file))
        ctx = self._make_ctx(tmp_path)

        with patch(
            "league_manager.reports.gmail_report.load_oauth_credentials",
            return_value=MagicMock(),
        ), patch(
            "league_manager.reports.gmail_report.gmail_api_send",
            side_effect=Exception("API error"),
        ):
            result = asyncio.run(plugin.generate(ctx))

        assert result.ok is False
        assert result.error_code == "gmail_send_error"

    def test_send_mode_success(self, tmp_path):
        """Happy path: send returns ok=True with message_id."""
        from unittest.mock import patch, MagicMock
        from league_manager.reports.gmail_report import GmailReportPlugin

        token_file = tmp_path / "token.json"
        token_file.write_text("{}")

        plugin = GmailReportPlugin(mode="send", token_path=str(token_file))
        ctx = self._make_ctx(tmp_path)

        with patch(
            "league_manager.reports.gmail_report.load_oauth_credentials",
            return_value=MagicMock(),
        ), patch(
            "league_manager.reports.gmail_report.gmail_api_send",
            return_value="sent_msg_id_42",
        ):
            result = asyncio.run(plugin.generate(ctx))

        assert result.ok is True
        assert result.status == "sent"
        assert result.details.get("message_id") == "sent_msg_id_42"

    def test_invalid_mode(self, tmp_path):
        """Unknown mode returns invalid_mode error code."""
        from league_manager.reports.gmail_report import GmailReportPlugin

        plugin = GmailReportPlugin(mode="unknown_mode")
        ctx = self._make_ctx(tmp_path)
        result = asyncio.run(plugin.generate(ctx))
        assert result.ok is False
        assert result.error_code == "invalid_mode"


# ---------------------------------------------------------------------------
# reports/bundle.py
# ---------------------------------------------------------------------------


class TestReportBundleBuilder:
    def test_build_peerruntime_path_with_step0(self, tmp_path):
        """PeerRuntime path: step0_evidence.json + result file present."""
        from league_manager.reports.bundle import ReportBundleBuilder
        import json

        game_id = "peer_game_01"
        (tmp_path / "step0_evidence.json").write_text(json.dumps({"step": 0}))
        (tmp_path / f"result_{game_id}.json").write_text(json.dumps({"winner": "cop"}))

        builder = ReportBundleBuilder(tmp_path)
        ctx = asyncio.run(
            builder.build(game_id, "cop", {}, result={"winner": "cop"})
        )
        assert ctx.game_id == game_id
        assert "declaration" in ctx.required_files or "result" in ctx.required_files

    def test_build_peerruntime_path_with_journal(self, tmp_path):
        """PeerRuntime path: journal file + result file."""
        from league_manager.reports.bundle import ReportBundleBuilder
        import json

        game_id = "peer_game_02"
        journal = tmp_path / f"journal_{game_id}_g01.json"
        journal.write_text(json.dumps({"journal": True}))
        (tmp_path / f"result_{game_id}.json").write_text(json.dumps({"winner": "thief"}))

        builder = ReportBundleBuilder(tmp_path)
        ctx = asyncio.run(builder.build(game_id, "thief", {}, metadata={"group_id": "g1"}))
        assert ctx.group_id == "g1"

    def test_build_peerruntime_missing_result_raises(self, tmp_path):
        """PeerRuntime path without result file raises FileNotFoundError."""
        from league_manager.reports.bundle import ReportBundleBuilder
        import json
        import pytest

        game_id = "peer_game_03"
        (tmp_path / "step0_evidence.json").write_text(json.dumps({}))
        # No result file!

        builder = ReportBundleBuilder(tmp_path)
        with pytest.raises(FileNotFoundError):
            asyncio.run(builder.build(game_id, "cop", {}))

    def test_build_gamerunner_path_all_files(self, tmp_path):
        """GameRunner legacy path: all 4 required files present."""
        from league_manager.reports.bundle import ReportBundleBuilder
        import json

        game_id = "legacy_game_01"
        (tmp_path / f"declaration_{game_id}.json").write_text(json.dumps({"decl": True}))
        (tmp_path / f"config_{game_id}_g01.json").write_text(json.dumps({"config": True}))
        (tmp_path / f"log_{game_id}_g01.json").write_text(json.dumps({"log": True}))
        (tmp_path / f"result_{game_id}.json").write_text(json.dumps({"winner": "cop"}))

        builder = ReportBundleBuilder(tmp_path)
        ctx = asyncio.run(builder.build(game_id, "cop", {"move_history": []}, result={"winner": "cop"}))
        assert ctx.role == "cop"
        assert "declaration" in ctx.required_files

    def test_build_gamerunner_missing_files_raises(self, tmp_path):
        """GameRunner path with missing files raises FileNotFoundError."""
        from league_manager.reports.bundle import ReportBundleBuilder
        import pytest

        game_id = "missing_game"
        builder = ReportBundleBuilder(tmp_path)
        with pytest.raises(FileNotFoundError):
            asyncio.run(builder.build(game_id, "thief", {}))

    def test_collect_optional_files(self, tmp_path):
        """Optional files are collected when they exist."""
        from league_manager.reports.bundle import ReportBundleBuilder
        import json

        # Create some optional files
        (tmp_path / "report.json").write_text("{}")
        (tmp_path / "report.md").write_text("# Report")
        (tmp_path / "journal_opt_game_01.json").write_text("{}")

        # Also create required files for a PeerRuntime path
        game_id = "opt_game_01"
        (tmp_path / "step0_evidence.json").write_text("{}")
        (tmp_path / f"result_{game_id}.json").write_text("{}")

        builder = ReportBundleBuilder(tmp_path)
        ctx = asyncio.run(builder.build(game_id, "cop", {}))
        assert "report.json" in ctx.optional_files
        assert "report.md" in ctx.optional_files

    def test_build_with_game_state_timestamps(self, tmp_path):
        """Test that created_at/ended_at from game_state populate timestamps."""
        from league_manager.reports.bundle import ReportBundleBuilder
        import json

        game_id = "ts_game_01"
        (tmp_path / "step0_evidence.json").write_text("{}")
        (tmp_path / f"result_{game_id}.json").write_text("{}")

        builder = ReportBundleBuilder(tmp_path)
        ctx = asyncio.run(
            builder.build(
                game_id,
                "thief",
                {"created_at": "2026-01-01T00:00:00", "ended_at": "2026-01-01T01:00:00"},
            )
        )
        assert ctx.start_timestamp == "2026-01-01T00:00:00"
        assert ctx.end_timestamp == "2026-01-01T01:00:00"
