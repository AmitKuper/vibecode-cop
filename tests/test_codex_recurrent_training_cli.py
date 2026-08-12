"""Evidence-contract tests for recurrent training — held-out scoring and CLI modes."""

import sys
from unittest.mock import patch

import pytest
import torch

from cop_worker.rl.action_space import COP_ACTIONS
from cop_worker.rl.local_obs_adapter import obs_tensor_shape
from cop_worker.rl.recurrent_policy import RecurrentActorCritic
from cop_worker.rl.train_recurrent import FAMILIES, evaluate


def test_evaluation_thief_scoring_and_cli_modes(monkeypatch, tmp_path) -> None:
    with patch("cop_worker.rl.train_recurrent._run_episode", return_value=([], "police", 3)):
        thief_result = evaluate(object(), "police", 1, 3, object(), inference_temperature=0.5)
    assert thief_result["official_role_score"] == len(FAMILIES) * 6 * 10
    assert thief_result["inference_mode"] == "low_temp"

    import cop_worker.rl.train_recurrent as training_module

    historical = tmp_path / "historical.pt"
    historical.write_bytes(b"historical")
    artifact = tmp_path / "cop_recurrent_champion.pt"
    network = RecurrentActorCritic(obs_tensor_shape(7), len(COP_ACTIONS), 8)
    torch.save(
        {
            "role": "cop",
            "input_size": obs_tensor_shape(7),
            "n_actions": len(COP_ACTIONS),
            "hidden_size": 8,
            "training_steps": 35,
            "state_dict": network.state_dict(),
        },
        artifact,
    )
    evidence = tmp_path / "evidence"
    models = tmp_path / "models"
    monkeypatch.setattr("cop_worker.rl.policy_loader.load_checkpoint", lambda *_a, **_kw: object())
    monkeypatch.setattr(training_module, "evaluate", lambda *_a, **_kw: {})
    monkeypatch.setattr(
        training_module, "_promotion_comparison", lambda *_a, **_kw: {"passed": True}
    )

    def invoke(*extra: str) -> None:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "train_recurrent",
                "--role",
                "cop",
                "--historical-checkpoint",
                str(historical),
                "--models-dir",
                str(models),
                "--evidence-dir",
                str(evidence),
                *extra,
            ],
        )
        training_module.main()

    invoke("--evaluate-only-artifact", str(artifact))
    assert (evidence / "cop_held_out_tournament.json").is_file()
    with pytest.raises(RuntimeError, match="temperature"):
        invoke("--evaluate-only-artifact", str(artifact), "--inference-temperature", "2")

    monkeypatch.setattr(training_module, "train", lambda *_a, **_kw: network)
    invoke("--episodes", "0", "--hidden-size", "8")
    invoke(
        "--episodes",
        "0",
        "--hidden-size",
        "8",
        "--resume-artifact",
        str(artifact),
    )
