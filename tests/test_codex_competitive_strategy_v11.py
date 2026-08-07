from __future__ import annotations

import random

import numpy as np
import torch

from cop_worker.belief_engine import BeliefEngine
from cop_worker.domain.types import DomainState
from cop_worker.language.deception_policy import DeceptionIntent, NaturalLanguagePolicy
from cop_worker.mcp.messages import ActionMessage, validate_action_message
from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.action_space import THIEF_ACTIONS
from cop_worker.rl.recurrent_policy import RecurrentRolePolicy
from cop_worker.rl.risk_mask import belief_safe_actions
from cop_worker.rl.train_recurrent import (
    COP_TRAINING_SCHEDULE,
    FAMILIES,
    _belief_trap_reward,
    _opponent_action,
)


def _belief(cell: tuple[int, int]) -> BeliefState:
    probability = np.zeros((7, 7))
    probability[cell[1], cell[0]] = 1.0
    return BeliefState(7, probability, entropy=0.0, confidence=1.0)


def test_held_out_population_has_diverse_required_families() -> None:
    assert len(FAMILIES) >= 8
    assert {
        "random",
        "belief_pursuit_evasion",
        "scent_following",
        "corridor_cutting",
        "anti_loop",
        "historical_checkpoint",
        "targeted_exploit",
        "deceptive_language",
    }.issubset(FAMILIES)


def test_cop_training_schedule_targets_the_exploit_without_dropping_coverage() -> None:
    assert set(FAMILIES).issubset(COP_TRAINING_SCHEDULE)
    assert COP_TRAINING_SCHEDULE.count("targeted_exploit") >= 4


def test_cop_trap_reward_uses_belief_supported_public_barrier_change() -> None:
    belief = _belief((3, 3))
    assert _belief_trap_reward(belief, [], [], 7) == 0.0
    assert _belief_trap_reward(belief, [], [(3, 2)], 7) > 0.0
    assert _belief_trap_reward(belief, [], [(0, 0)], 7) == 0.0


def test_new_opponents_use_only_local_belief_scent_and_public_state() -> None:
    state = DomainState(
        turn=4,
        grid_size=7,
        cop_position=(2, 2),
        thief_position=(5, 5),
        barriers=[(3, 3)],
        cop_barriers_remaining=10,
        move_history=[],
        scent_grid=[[0.0] * 7 for _ in range(7)],
    )
    belief = BeliefEngine(7, "cop")
    belief._belief = _belief((5, 4))
    scent = [[0.0] * 7 for _ in range(7)]
    scent[4][5] = 0.9
    for family in (
        "scent_following",
        "corridor_cutting",
        "anti_loop",
        "targeted_exploit",
        "deceptive_language",
    ):
        action = _opponent_action(
            state,
            "cop",
            family,
            random.Random(17),
            opponent_scent=scent,
            opponent_belief=belief,
        )
        assert isinstance(action, str)


def test_belief_risk_mask_retains_legal_choice_and_removes_peak_risk() -> None:
    legal = list(THIEF_ACTIONS)
    safe = belief_safe_actions((3, 3), _belief((4, 3)), legal, [])
    assert safe
    assert set(safe) < set(legal)
    assert "E" not in safe
    assert len(safe) >= 2


class _RiskyEastNetwork(torch.nn.Module):
    def forward(self, features, hidden):
        logits = torch.zeros((features.shape[0], len(THIEF_ACTIONS)))
        logits[:, THIEF_ACTIONS.index("E")] = 100.0
        logits[:, THIEF_ACTIONS.index("W")] = 50.0
        next_hidden = torch.zeros((features.shape[0], 8))
        return logits, torch.zeros((features.shape[0], 1)), next_hidden


def test_deployed_thief_uses_trained_preference_after_legal_mask() -> None:
    policy = RecurrentRolePolicy(_RiskyEastNetwork(), "police", torch.device("cpu"))
    observation = LocalObservation(
        own_position=(3, 3),
        own_barriers_remaining=0,
        known_barriers=[],
        opponent_scent=[[0.0] * 7 for _ in range(7)],
        last_hint="",
        step=1,
        gamelet=1,
        grid_size=7,
    )
    action = policy.select_action(observation, _belief((4, 3)), list(THIEF_ACTIONS))
    assert action == "E"


def test_all_four_language_intents_survive_wire_validation() -> None:
    for intent in DeceptionIntent:
        message = ActionMessage(
            game_id="game_g1",
            step=1,
            role="police",
            config_sha256="0" * 64,
            timestamp="2026-08-06T00:00:00Z",
            phase="reveal",
            move="STAY",
            hint="Making a strategic move.",
            intent=intent.value,
            state_hash="1" * 64,
        )
        assert validate_action_message(message) == (True, None)


def test_language_policy_consumes_context_and_low_token_budget() -> None:
    policy = NaturalLanguagePolicy("police")
    assert (
        policy.choose_intent(
            7,
            belief_entropy=3.0,
            trust_history=[True, False],
            gamelet=4,
            physical_action="E",
            token_budget=4,
        )
        is DeceptionIntent.AMBIGUOUS
    )
