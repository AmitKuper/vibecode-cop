"""Fail-closed AgentOrchestrator precondition and role-branch contracts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent.agent_orchestrator import AgentOrchestrator
from agent.runtime_mode import RuntimeMode


def _orchestrator(config, role="cop"):
    orchestrator = object.__new__(AgentOrchestrator)
    orchestrator.config = config
    orchestrator.role = role
    return orchestrator


def _entry(**overrides):
    values = {
        "training_steps": 100,
        "evaluation_win_rate": 0.8,
        "sha256": "model-sha",
        "config_sha256": "config-sha",
        "inference_mode": "argmax",
        "hyperparams": {},
        "is_compatible": lambda _role, _grid: (True, ""),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _config(tmp_path, **overrides):
    manifest = tmp_path / "MANIFEST.json"
    manifest.write_text("{}", encoding="utf-8")
    values = {
        "secret": "production-secret",
        "model_sha256": "model-sha",
        "gmail_sender": lambda *_args: "id",
        "model_manifest_path": str(manifest),
        "config_sha256": "config-sha",
        "grid_size": 7,
    }
    values.update(overrides)
    return values


def _validate(monkeypatch, tmp_path, *, config=None, entry=None, manifest=None):
    chosen_config = config or _config(tmp_path)
    chosen_manifest = {"cop": entry or _entry()} if manifest is None else manifest
    monkeypatch.setattr("subprocess.check_output", lambda *_args, **_kwargs: "a" * 40)
    monkeypatch.setattr("agent.rl.model_schema.load_manifest", lambda _path: chosen_manifest)
    _orchestrator(chosen_config)._validate_counted_preconditions()


def test_counted_preconditions_accept_argmax_and_valid_low_temp(monkeypatch, tmp_path) -> None:
    _validate(monkeypatch, tmp_path)
    _validate(
        monkeypatch,
        tmp_path,
        entry=_entry(
            inference_mode="low_temp",
            hyperparams={"inference_temperature": 0.2},
        ),
    )


@pytest.mark.parametrize(
    ("entry", "match"),
    [
        (_entry(training_steps=0), "training_steps=0"),
        (_entry(evaluation_win_rate=0.0), "evaluation_win_rate=0.0"),
        (_entry(is_compatible=lambda _role, _grid: (False, "wrong grid")), "incompatible"),
        (_entry(sha256="different"), "SHA does not match"),
        (_entry(config_sha256="different"), "config SHA does not match"),
        (_entry(inference_mode="random"), "inference mode is unsupported"),
        (
            _entry(inference_mode="low_temp", hyperparams={"inference_temperature": 0}),
            "temperature is invalid",
        ),
        (
            _entry(inference_mode="low_temp", hyperparams={"inference_temperature": 2}),
            "temperature is invalid",
        ),
    ],
)
def test_counted_preconditions_reject_model_metadata(monkeypatch, tmp_path, entry, match) -> None:
    with pytest.raises(ValueError, match=match):
        _validate(monkeypatch, tmp_path, entry=entry)


def test_counted_preconditions_reject_identity_gmail_and_manifest_failures(
    monkeypatch, tmp_path
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr("subprocess.check_output", lambda *_args, **_kwargs: "not-a-sha")
    with pytest.raises(ValueError, match="git SHA invalid"):
        _orchestrator(config)._validate_counted_preconditions()

    class BrokenSender:
        def __call__(self, *_args):
            return "never"

        def validate(self):
            raise RuntimeError("oauth offline")

    with pytest.raises(ValueError, match="Gmail sender unavailable"):
        _validate(
            monkeypatch,
            tmp_path,
            config=_config(tmp_path, gmail_sender=BrokenSender()),
        )
    with pytest.raises(ValueError, match="not configured"):
        _validate(monkeypatch, tmp_path, config=_config(tmp_path, gmail_sender=object()))
    with pytest.raises(ValueError, match="no model for role"):
        _validate(monkeypatch, tmp_path, manifest={})

    missing = _config(tmp_path, model_manifest_path=str(tmp_path / "missing.json"))
    with pytest.raises(ValueError, match="manifest not found"):
        _validate(monkeypatch, tmp_path, config=missing)


def test_orchestrator_role_policy_and_watchdog_failure_branches(tmp_path) -> None:
    orchestrator = object.__new__(AgentOrchestrator)
    orchestrator.role = "thief"
    orchestrator.grid_size = 7
    orchestrator.movement_policy = None
    orchestrator.scent_fields = SimpleNamespace(
        cop_observation_scent=lambda: [[1.0]],
        thief_observation_scent=lambda: [[2.0]],
    )
    orchestrator.belief_engine = SimpleNamespace(belief="belief")

    orchestrator.reset_movement_history()
    assert len(orchestrator.get_action_names()) > 0
    assert any(orchestrator.get_legal_mask((3, 3), []))
    with pytest.raises(RuntimeError, match="unavailable"):
        orchestrator.select_trained_move(
            own_position=(3, 3),
            barriers=[],
            barriers_remaining=0,
            legal_actions=["STAY"],
            step=1,
            gamelet=1,
        )

    policy = MagicMock()
    policy.select_action.return_value = "STAY"
    orchestrator.movement_policy = policy
    orchestrator.reset_movement_history()
    assert (
        orchestrator.select_trained_move(
            own_position=(3, 3),
            barriers=[],
            barriers_remaining=0,
            legal_actions=["STAY"],
            step=1,
            gamelet=1,
        )
        == "STAY"
    )
    policy.reset.assert_called_once()

    orchestrator.mode = RuntimeMode.COUNTED
    orchestrator.work_dir = str(tmp_path)
    orchestrator.game_uid = "series_g01"
    orchestrator.config = {"private_config": {"timeouts": {"watchdog_threshold_seconds": 0}}}
    orchestrator._watchdog_proc = None
    with (
        patch.object(orchestrator, "emit_heartbeat"),
        pytest.raises(RuntimeError, match="watchdog failed to start"),
    ):
        orchestrator.start_watchdog()
