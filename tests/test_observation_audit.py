"""Tests for Phase 3D: observation audit / leak detection."""

from __future__ import annotations

import pytest

from agent.observation_audit import audit_observation_for_leaks


class TestAuditObservationForLeaks:
    def test_clean_obs_no_leaks(self):
        obs = {
            "own_position": [2, 3],
            "scent_field": [[0.1, 0.2], [0.3, 0.4]],
            "turn": 5,
        }
        leaks = audit_observation_for_leaks(obs, "cop", (2, 3), (5, 6))
        assert leaks == []

    def test_thief_obs_with_cop_position_in_grid_state(self):
        obs = {
            "own_position": [2, 3],
            "grid_state": {
                "thief_position": [2, 3],
                "cop_position": [5, 6],  # hidden coordinate — leak!
                "turn": 5,
            },
        }
        leaks = audit_observation_for_leaks(obs, "thief", (2, 3), (5, 6))
        assert len(leaks) > 0
        assert any("cop_position" in leak for leak in leaks)

    def test_cop_obs_with_thief_position_in_grid_state(self):
        obs = {
            "own_position": [5, 6],
            "grid_state": {
                "cop_position": [5, 6],
                "thief_position": [2, 3],  # hidden coordinate — leak!
                "turn": 5,
            },
        }
        leaks = audit_observation_for_leaks(obs, "cop", (5, 6), (2, 3))
        assert len(leaks) > 0
        assert any("thief_position" in leak for leak in leaks)

    def test_no_grid_state_no_leak(self):
        obs = {
            "own_position": [2, 3],
            "candidate_actions": ["N", "S"],
            "scent_field": [[0.0]],
        }
        leaks = audit_observation_for_leaks(obs, "thief", (2, 3), (5, 6))
        assert leaks == []

    def test_grid_state_without_opponent_key_no_leak(self):
        obs = {
            "grid_state": {
                "thief_position": [2, 3],  # own position for thief role
                "turn": 5,
                "barriers": [],
            },
        }
        leaks = audit_observation_for_leaks(obs, "thief", (2, 3), (5, 6))
        # thief_position is own position, not opponent — no leak
        assert leaks == []

    def test_leak_message_informative(self):
        obs = {
            "grid_state": {
                "cop_position": [5, 6],
            },
        }
        leaks = audit_observation_for_leaks(obs, "thief", (2, 3), (5, 6))
        assert leaks
        assert "grid_state" in leaks[0]
