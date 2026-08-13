"""Cover the validation/error branches of ObservationProcessor."""

from __future__ import annotations

import pytest

from cop_worker.observation_processor import (
    ObservationProcessor,
    ObservationProcessorError,
)


def test_normalise_turn_rejects_unknown_kind():
    p = ObservationProcessor()
    with pytest.raises(ObservationProcessorError, match="Unknown turn kind"):
        p.normalise_turn({"kind": "bogus", "step": 1})


def test_normalise_turn_rejects_non_int_step():
    p = ObservationProcessor()
    with pytest.raises(ObservationProcessorError, match="step must be int"):
        p.normalise_turn({"kind": "commit", "step": "1"})


def test_normalise_turn_accepts_full_payload():
    p = ObservationProcessor()
    turn = p.normalise_turn(
        {
            "kind": "reveal",
            "step": 2,
            "nonce": "n",
            "action": {"a": 1},
            "smell_grid": {"0,0": 0.1},
            "hint": "go",
        }
    )
    assert turn.kind == "reveal" and turn.step == 2 and turn.hint == "go"


def test_normalise_audit_rejects_missing_field():
    p = ObservationProcessor()
    with pytest.raises(ObservationProcessorError, match="missing required field"):
        p.normalise_audit({"game_uid": "g"})


def test_normalise_audit_accepts_complete_payload():
    p = ObservationProcessor()
    audit = p.normalise_audit(
        {
            "game_uid": "g",
            "sub_game_number": 1,
            "role": "cop",
            "steps": [],
            "terminal_condition": "capture",
            "final_step": 3,
            "log_hash": "h",
        }
    )
    assert audit.final_step == 3 and audit.role == "cop"


def test_normalise_control_requires_kind():
    p = ObservationProcessor()
    with pytest.raises(ObservationProcessorError, match="missing 'kind'"):
        p.normalise_control({"reason": "x"})
    msg = p.normalise_control({"kind": "abort", "reason": "peer left"})
    assert msg.kind == "abort" and msg.reason == "peer left"
