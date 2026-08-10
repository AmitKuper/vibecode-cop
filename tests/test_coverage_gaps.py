"""Targeted tests for modules the 2026-08-10 additions left under the CI coverage gate.

Each block earns its place by pinning real behaviour: the scent fingerprint's model
classification (log-only, but it fed a live MISMATCH banner), the obs-mode env contract,
the Dueling counted-policy loader's refusal branches, and the small pure utilities
(phase tracker, live view model, message validators, dual logging).
"""

from __future__ import annotations

import hashlib
import logging
from types import SimpleNamespace

import pytest
import torch

# ---------------------------------------------------------------------------
# cop_worker.protocol.scent_fingerprint
# ---------------------------------------------------------------------------
from cop_worker.protocol.scent_fingerprint import agrees_with_us, fingerprint


class TestScentFingerprint:
    def test_book_fresh_field_classifies_book(self) -> None:
        grid = {"3,3": 0.9, "3,4": 0.62, "3,5": 0.42, "2,2": 0.14, "1,1": 0.04}
        result = fingerprint(grid)
        assert result["model"] == "multiplicative_book_v1"
        assert result["book_only_hits"] >= 3
        assert result["sha256"].startswith("934c220d")

    def test_chebyshev_fresh_rings_classify_chebyshev(self) -> None:
        result = fingerprint({"3,3": 0.9, "3,4": 0.6, "3,5": 0.3})
        assert result["model"] == "subtractive_chebyshev_v1"
        assert result["sha256"].startswith("81ebee59")

    def test_decayed_chebyshev_lattice_classifies_chebyshev(self) -> None:
        # The kit's own wire frame: after-one-decay {0.8, 0.5, 0.2} — the exact live
        # frame that misclassified as book before the 0.1-lattice rule.
        result = fingerprint({"3,3": 0.8, "3,4": 0.5, "3,5": 0.2, "2,3": 0.5})
        assert result["model"] == "subtractive_chebyshev_v1"

    def test_two_lattice_cells_are_not_decisive(self) -> None:
        # 0.2/0.9 exist in both models; fewer than three cells never decide.
        assert fingerprint({"0,0": 0.2, "1,1": 0.9})["model"] == "inconclusive"

    def test_empty_and_mixed_evidence(self) -> None:
        assert fingerprint({})["model"] == "empty"
        assert fingerprint(None)["model"] == "empty"
        mixed = fingerprint({"1,1": 0.62, "2,2": 0.6, "3,3": 0.3})
        assert mixed["model"] == "inconclusive"

    def test_agrees_with_us_tri_state(self) -> None:
        assert agrees_with_us({"3,3": 0.9, "3,4": 0.62, "2,2": 0.42}) is True
        assert agrees_with_us({"3,3": 0.9, "3,4": 0.6, "3,5": 0.3}) is False
        assert agrees_with_us({}) is None


# ---------------------------------------------------------------------------
# cop_worker.rl.obs_mode
# ---------------------------------------------------------------------------
from cop_worker.rl import obs_mode


class TestObsMode:
    def test_unknown_scent_model_is_a_configuration_error(self, monkeypatch) -> None:
        monkeypatch.setenv(obs_mode.SCENT_MODEL_ENV, "no_such_model")
        with pytest.raises(ValueError, match="not a registered scent model"):
            obs_mode.scent_model()

    def test_shorthands_resolve_to_registered_names(self, monkeypatch) -> None:
        monkeypatch.setenv(obs_mode.SCENT_MODEL_ENV, "chebyshev")
        assert obs_mode.scent_model() == "subtractive_chebyshev_v1"
        assert obs_mode.chebyshev_scent_enabled() is True
        monkeypatch.setenv(obs_mode.SCENT_MODEL_ENV, "book")
        assert obs_mode.scent_model() == "multiplicative_book_v1"

    def test_describe_and_tag_reflect_all_switches(self, monkeypatch) -> None:
        monkeypatch.setenv(obs_mode.UNIFORM_BELIEF_ENV, "1")
        monkeypatch.setenv(obs_mode.WIRE_SCENT_ENV, "1")
        monkeypatch.setenv(obs_mode.DECODED_SCENT_ENV, "1")
        monkeypatch.setenv(obs_mode.SCENT_MODEL_ENV, "chebyshev")
        described = obs_mode.describe()
        assert described == {
            "uniform_belief": True,
            "wire_scent": True,
            "decoded_scent": True,
            "scent_model": "subtractive_chebyshev_v1",
        }
        tag = obs_mode.observation_mode_tag()
        for part in ("uniformbelief", "wirescent", "decodedscent", "chebyshev"):
            assert part in tag

    def test_legacy_tag_when_everything_off(self, monkeypatch) -> None:
        for env in (
            obs_mode.UNIFORM_BELIEF_ENV,
            obs_mode.WIRE_SCENT_ENV,
            obs_mode.DECODED_SCENT_ENV,
            obs_mode.SCENT_MODEL_ENV,
        ):
            monkeypatch.delenv(env, raising=False)
        assert obs_mode.observation_mode_tag() == "legacy-research-obs"


# ---------------------------------------------------------------------------
# cop_worker.rl.counted_policy — the Dueling loader + its refusal branches
# ---------------------------------------------------------------------------
from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.counted_policy import (
    CountedPolicyLoadError,
    DuelingDoubleQNetwork,
    DuelingDoubleQRolePolicy,
    _load_dueling_policy,
)
from cop_worker.rl.local_obs_adapter import obs_tensor_shape


def _dueling_checkpoint(tmp_path, **overrides):
    payload = {
        "role": "thief",
        "algorithm": "DuelingDoubleDQN",
        "input_size": obs_tensor_shape(7),
        "n_actions": 5,
        "hidden_size": 32,
    }
    payload.update(overrides)
    net = DuelingDoubleQNetwork(payload["input_size"], payload["n_actions"], payload["hidden_size"])
    payload["state_dict"] = net.state_dict()
    artifact = tmp_path / "thief_test.pt"
    torch.save(payload, artifact)
    sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    entry = SimpleNamespace(
        inference_mode="argmax",
        artifact=artifact.name,
        sha256=sha,
        algorithm="DuelingDoubleDQN",
    )
    return tmp_path / "MANIFEST.json", entry


class TestDuelingLoader:
    def test_happy_path_loads_and_selects_a_legal_action(self, tmp_path) -> None:
        manifest, entry = _dueling_checkpoint(tmp_path)
        policy = _load_dueling_policy(manifest, entry, "thief")
        assert isinstance(policy, DuelingDoubleQRolePolicy)
        obs = LocalObservation(
            own_position=(3, 3),
            own_barriers_remaining=0,
            known_barriers=[],
            opponent_scent=[[0.0] * 7 for _ in range(7)],
            last_hint="",
            step=1,
            gamelet=1,
            grid_size=7,
        )
        action = policy.select_action(obs, BeliefState.uniform(7, step=1), ["N", "S"])
        assert action in {"N", "S"}
        policy.reset()  # no decoder configured: must be a no-op, never raise

    def test_no_legal_actions_is_a_hard_error(self, tmp_path) -> None:
        manifest, entry = _dueling_checkpoint(tmp_path)
        policy = _load_dueling_policy(manifest, entry, "thief")
        obs = LocalObservation(
            own_position=(3, 3),
            own_barriers_remaining=0,
            known_barriers=[],
            opponent_scent=[[0.0] * 7 for _ in range(7)],
            last_hint="",
            step=1,
            gamelet=1,
            grid_size=7,
        )
        with pytest.raises(RuntimeError, match="no legal actions"):
            policy.select_action(obs, BeliefState.uniform(7, step=1), [])

    def test_role_mismatch_refuses(self, tmp_path) -> None:
        manifest, entry = _dueling_checkpoint(tmp_path)
        with pytest.raises(CountedPolicyLoadError, match="role"):
            _load_dueling_policy(manifest, entry, "cop")

    def test_wrong_input_size_refuses(self, tmp_path) -> None:
        manifest, entry = _dueling_checkpoint(tmp_path, input_size=17)
        with pytest.raises(CountedPolicyLoadError, match="observation tensor"):
            _load_dueling_policy(manifest, entry, "thief")

    def test_wrong_action_count_refuses(self, tmp_path) -> None:
        manifest, entry = _dueling_checkpoint(tmp_path, n_actions=9)
        with pytest.raises(CountedPolicyLoadError, match="action schema"):
            _load_dueling_policy(manifest, entry, "thief")

    def test_non_argmax_inference_refuses(self, tmp_path) -> None:
        manifest, entry = _dueling_checkpoint(tmp_path)
        entry.inference_mode = "sample"
        with pytest.raises(CountedPolicyLoadError, match="argmax"):
            _load_dueling_policy(manifest, entry, "thief")

    def test_missing_artifact_refuses(self, tmp_path) -> None:
        manifest, entry = _dueling_checkpoint(tmp_path)
        entry.artifact = "no_such_file.pt"
        with pytest.raises(CountedPolicyLoadError, match="not found"):
            _load_dueling_policy(manifest, entry, "thief")


# ---------------------------------------------------------------------------
# cop_worker.mcp.protocol_phases
# ---------------------------------------------------------------------------
from cop_worker.mcp.protocol import ProtocolPhase
from cop_worker.mcp.protocol_phases import StepPhaseTracker


class TestStepPhaseTracker:
    def test_both_at_phase_requires_both_roles(self) -> None:
        tracker = StepPhaseTracker()
        phase = list(ProtocolPhase)[0]
        assert tracker.both_at_phase(1, phase) is False
        tracker.mark_phase(1, "cop", phase)
        assert tracker.both_at_phase(1, phase) is False
        tracker.mark_phase(1, "police", phase)
        assert tracker.both_at_phase(1, phase) is True
        assert tracker.to_dict() == {1: {"cop": phase.value, "police": phase.value}}


# ---------------------------------------------------------------------------
# cop_worker.gui.live_view_model
# ---------------------------------------------------------------------------
from cop_worker.gui.live_view_model import LiveViewModel
from cop_worker.observation import SafeLiveView


def _view() -> SafeLiveView:
    return SafeLiveView(
        own_position=(1, 2),
        belief_heatmap=[[1.0 / 49] * 7 for _ in range(7)],
        opponent_scent=[[0.0] * 7 for _ in range(7)],
        last_hint="",
        hint_reliability=0.5,
        turn=3,
        gamelet=1,
        score={"cop": 0, "thief": 0},
        own_barriers_remaining=14,
        protocol_state="PLAYING",
        your_turn=True,
        connection_healthy=True,
    )


class TestLiveViewModel:
    def test_update_then_read_round_trips_without_hidden_coords(self) -> None:
        model = LiveViewModel("cop", 7)
        assert model.get_current() is None
        assert model.get_update() is None
        model.update(_view())
        assert model.get_current().own_position == (1, 2)
        update = model.get_update()
        assert update is not None
        payload = update.to_json()
        assert '"turn": 3' in payload


# ---------------------------------------------------------------------------
# cop_worker.mcp.messages — the validators
# ---------------------------------------------------------------------------
from cop_worker.mcp.messages import (
    ActionMessage,
    MessagePhase,
    StartGameMessage,
    validate_action_message,
    validate_start_game_message,
)

_SHA = "a" * 64


class TestMessageValidators:
    def test_start_game_happy_path(self) -> None:
        msg = StartGameMessage(
            game_id="g1",
            roles={"cop": "a", "police": "b"},
            config_sha256=_SHA,
            protocol_version="1.0",
            endpoint="http://localhost:5000/mcp",
            timestamp="2026-08-10T20:00:00+03:00",
        )
        assert validate_start_game_message(msg) == (True, None)

    @pytest.mark.parametrize(
        ("field", "value", "hint"),
        [
            ("game_id", "", "game_id"),
            ("roles", {"cop": "a"}, "roles"),
            ("config_sha256", "short", "config_sha256"),
            ("protocol_version", "2.0", "protocol_version"),
            ("endpoint", "not-a-url", "endpoint"),
            ("timestamp", "", "timestamp"),
        ],
    )
    def test_start_game_refusals(self, field, value, hint) -> None:
        msg = StartGameMessage(
            game_id="g1",
            roles={"cop": "a", "police": "b"},
            config_sha256=_SHA,
            protocol_version="1.0",
            endpoint="http://localhost:5000/mcp",
            timestamp="t",
        )
        setattr(msg, field, value)
        ok, err = validate_start_game_message(msg)
        assert ok is False and hint in err

    def test_action_message_happy_and_refusals(self) -> None:
        msg = ActionMessage(
            game_id="g1",
            step=1,
            role="cop",
            config_sha256=_SHA,
            timestamp="t",
            phase=MessagePhase.COMMIT.value,
            h_commit=_SHA,
        )
        assert validate_action_message(msg)[0] is True
        msg.step = -1
        assert validate_action_message(msg)[0] is False
        msg.step = 1
        msg.role = "spectator"
        assert validate_action_message(msg)[0] is False
        msg.role = "cop"
        msg.phase = "no_such_phase"
        assert validate_action_message(msg)[0] is False


# ---------------------------------------------------------------------------
# cop_worker.logging_setup
# ---------------------------------------------------------------------------
from cop_worker.logging_setup import setup_dual_logging


class TestDualLogging:
    def test_creates_timestamped_file_and_logs_to_it(self, tmp_path) -> None:
        root = logging.getLogger()
        previous = root.handlers[:]
        try:
            log_file = setup_dual_logging(prefix="covtest", log_dir=tmp_path)
            logging.getLogger("covtest").info("hello coverage")
            for handler in root.handlers:
                handler.flush()
            assert log_file.exists()
            assert "hello coverage" in log_file.read_text(encoding="utf-8")
        finally:
            for handler in root.handlers[:]:
                if handler not in previous:
                    handler.close()
                    root.removeHandler(handler)
            for handler in previous:
                if handler not in root.handlers:
                    root.addHandler(handler)


# ---------------------------------------------------------------------------
# cop_worker.domain.config_validator + runtime_transition
# ---------------------------------------------------------------------------
from cop_worker.board import Board
from cop_worker.domain.config_validator import GameConfig
from cop_worker.domain.runtime_transition import (
    IllegalJointActionError,
    apply_runtime_transition,
    legal_actions_for_role,
    locked_config,
    state_from_runtime,
)
from cop_worker.rules_engine import RulesEngine


class TestConfigValidator:
    def test_appendix_f_violations_are_named(self) -> None:
        with pytest.raises(ValueError, match="max_barriers must be 14"):
            GameConfig(max_barriers=10)
        with pytest.raises(ValueError, match="grid_size must be >= 7"):
            GameConfig(grid_size=5)
        with pytest.raises(ValueError, match="max_moves must be >= 35"):
            GameConfig(max_moves=20)

    def test_defaults_are_the_signed_terms(self) -> None:
        cfg = GameConfig()
        assert (cfg.grid_size, cfg.max_barriers, cfg.max_moves) == (7, 14, 35)
        assert cfg.scoring.capture_cop == 20 and cfg.scoring.survival_thief == 10


class _Runtime:
    """Minimal stand-in for the legacy runtime the bridge synchronizes."""

    def __init__(self) -> None:
        self.board = Board(cop_position=[0, 0], thief_position=[3, 3], grid_size=7)
        self._cop_barriers_remaining = 14


class TestRuntimeTransition:
    def test_locked_config_falls_back_to_defaults(self) -> None:
        assert isinstance(locked_config(_Runtime()), GameConfig)

    def test_apply_synchronizes_board_and_caches_state(self) -> None:
        runtime = _Runtime()
        rules = RulesEngine(runtime.board)
        result = apply_runtime_transition(runtime, rules, "E", "W")
        assert result.cop_action_legal and result.thief_action_legal
        assert runtime.board.cop_position == [1, 0]
        assert runtime.board.thief_position == [2, 3]
        # The cached DomainState short-circuits the next rebuild.
        assert state_from_runtime(runtime, rules) is runtime._domain_state

    def test_illegal_joint_action_names_the_offender(self) -> None:
        runtime = _Runtime()
        rules = RulesEngine(runtime.board)
        with pytest.raises(IllegalJointActionError, match="cop"):
            apply_runtime_transition(runtime, rules, "W", "STAY")  # cop off-board

    def test_legal_actions_per_role_respect_the_edges(self) -> None:
        runtime = _Runtime()
        rules = RulesEngine(runtime.board)
        cop_legal = legal_actions_for_role(runtime, rules, "cop")
        thief_legal = legal_actions_for_role(runtime, rules, "thief")
        assert "W" not in cop_legal and "N" not in cop_legal  # corner (0,0)
        assert set(thief_legal) >= {"N", "S", "E", "W", "STAY"}  # centre (3,3)


class TestRemainingBranches:
    def test_survival_threshold_violation_named(self) -> None:
        with pytest.raises(ValueError, match="survival_threshold must be >= 35"):
            GameConfig(survival_threshold=10)

    def test_illegal_action_error_message_names_both_actions(self) -> None:
        err = IllegalJointActionError(("cop",), "W", "STAY")
        assert "cop" in str(err) and "'W'" in str(err)

    def test_locked_config_returns_the_runtime_config_when_set(self) -> None:
        runtime = _Runtime()
        runtime.game_config = GameConfig()
        assert locked_config(runtime) is runtime.game_config


# ---------------------------------------------------------------------------
# cop_worker.mcp.discovery — everything except the network call
# ---------------------------------------------------------------------------
from cop_worker.mcp.discovery import ProtocolDiscovery


class TestProtocolDiscovery:
    def test_sse_url_derivation_and_empty_state(self) -> None:
        disc = ProtocolDiscovery("http://localhost:5001/mcp")
        assert disc._sse_url == "http://localhost:5001/sse"
        assert disc.discovered is False
        assert disc.get_tool_names() == []
        assert disc.has_tool("negotiate") is False
        assert disc.get_tool_schema("negotiate") is None

    def test_validation_and_serialization_over_discovered_tools(self) -> None:
        disc = ProtocolDiscovery("http://localhost:5001/mcp")
        disc.tools = {
            "negotiate": {"name": "negotiate", "description": "", "schema": {}},
            "receive_turn": {"name": "receive_turn", "description": "", "schema": {}},
        }
        disc.discovered = True
        ok, msg = disc.validate_protocol(["negotiate", "receive_turn"])
        assert ok is True and "available" in msg
        ok, msg = disc.validate_protocol(["negotiate", "submit_audit"])
        assert ok is False and "submit_audit" in msg
        assert (
            disc.has_tool("negotiate") and disc.get_tool_schema("negotiate")["name"] == "negotiate"
        )
        serialized = disc.to_dict()
        assert serialized["discovered"] is True
        assert sorted(serialized["tools"]) == ["negotiate", "receive_turn"]

    @pytest.mark.anyio
    async def test_discover_failure_path_returns_false(self) -> None:
        # No server behind this port: the network branch must fail CLOSED (False),
        # never raise into the caller.
        disc = ProtocolDiscovery("http://127.0.0.1:9/mcp", timeout_seconds=0.5)
        assert await disc.discover() is False
        assert disc.discovered is False
