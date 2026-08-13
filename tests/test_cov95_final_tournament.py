"""Cover load_policy ddqn/legacy branches and main() in research_final_tournament."""

from __future__ import annotations

import json

import torch

from cop_worker.rl import research_final_tournament as rft
from cop_worker.rl.action_space import THIEF_ACTIONS
from cop_worker.rl.networks import PPONet
from cop_worker.rl.research_evaluation import LegacyResearchPolicy


def test_load_policy_ddqn_delegates(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(rft, "load_dqn_policy", lambda path, role: sentinel)
    assert rft.load_policy("ddqn:/tmp/x.pt", "cop") is sentinel


def test_load_policy_legacy(tmp_path):
    path = tmp_path / "thief_ppo.pt"
    net = PPONet(grid_size=7, n_actions=len(THIEF_ACTIONS), hidden=16, in_channels=4)
    torch.save(
        {"net": net.state_dict(), "updates": 1, "n_actions": len(THIEF_ACTIONS), "n_channels": 4},
        path,
    )
    policy = rft.load_policy(f"legacy:{path}", "thief")
    assert isinstance(policy, LegacyResearchPolicy)


def test_main_writes_and_prints_report(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rft, "load_policy", lambda spec, role: object())
    monkeypatch.setattr(
        rft, "evaluate_families", lambda *a, **kw: {"role": "cop", "held_out_series": 3}
    )
    out = tmp_path / "nested" / "tourney.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "--role",
            "cop",
            "--candidate",
            "scripted:anti_loop",
            "--historical-opponent",
            "scripted:anti_loop",
            "--series-per-family",
            "1",
            "--output",
            str(out),
        ],
    )
    rft.main()
    payload = json.loads(out.read_text())
    assert payload["role"] == "cop"
    assert "held_out_series" in capsys.readouterr().out
