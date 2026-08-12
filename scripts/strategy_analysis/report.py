"""Checkpoint loading and row/CSV emission for the strategy ablations."""

from __future__ import annotations

import csv
from pathlib import Path

import torch
from agent.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
from agent.rl.recurrent_policy import RecurrentActorCritic


def _load_network(path: Path, role: str) -> RecurrentActorCritic:
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if checkpoint.get("role") != role:
        raise RuntimeError(f"artifact role mismatch: {checkpoint.get('role')!r}")
    network = RecurrentActorCritic(
        int(checkpoint["input_size"]),
        int(checkpoint["n_actions"]),
        int(checkpoint["hidden_size"]),
    )
    expected_actions = len(COP_ACTIONS if role == "cop" else THIEF_ACTIONS)
    if int(checkpoint["n_actions"]) != expected_actions:
        raise RuntimeError("artifact action schema mismatch")
    network.load_state_dict(checkpoint["state_dict"])
    return network.eval()


def _summary(name: str, result: dict, note: str) -> dict:
    return {
        "variant": name,
        "note": note,
        "series": result["held_out_series"],
        "gamelets": result["held_out_games"],
        "win_rate": result["win_rate"],
        "series_win_rate": result["series_win_rate"],
        "official_role_score": result["official_role_score"],
        "official_opponent_score": result["official_opponent_score"],
        "score_differential": result["official_role_score"] - result["official_opponent_score"],
        "worst_family_win_rate": result["worst_family_win_rate"],
        "average_turns": result["average_turns"],
        "illegal_action_rate": result["illegal_action_rate"],
        "p99_inference_ms": result["inference_latency_ms"]["p99"],
        "technical_failures": result["technical_failures"],
    }


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
