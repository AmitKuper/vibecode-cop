"""Adversarial tests for Step-0-anchored canonical replay."""

from __future__ import annotations

import json
from pathlib import Path

from cop_worker.audit.result_consensus import GameletOutcome, ResultAgreement
from cop_worker.replay.replay_app import ReplayApp
from cop_worker.step0.signing import generate_key_pair, sign
from tests.helpers_replay_fixture import _fixture, _load, _resign


def test_load_reconstructs_valid_six_gamelet_result(tmp_path):
    app = ReplayApp()
    assert _load(app, _fixture(tmp_path)) is True
    verified, reason = app.verification_status()
    assert verified is True and reason == ""
    assert app.current_state().canonical_state["turn"] == 1


def test_result_self_supplied_key_cannot_replace_step0_trust(tmp_path):
    fixture = _fixture(tmp_path)
    result_path = fixture[0]
    data = json.loads(result_path.read_text(encoding="utf-8"))
    attacker_private, attacker_public = generate_key_pair()
    data["agreement"]["public_key_hex"] = attacker_public.hex()
    raw = dict(data["agreement"])
    raw["gamelet_outcomes"] = [GameletOutcome(**item) for item in raw["gamelet_outcomes"]]
    agreement = ResultAgreement(**raw)
    forged = sign(attacker_private, agreement.canonical_bytes()).hex()
    data["local_signature_hex"] = forged
    data["remote_signature_hex"] = forged
    result_path.write_text(json.dumps(data), encoding="utf-8")
    app = ReplayApp()
    assert _load(app, fixture) is False
    assert "trusted Step-0" in app.verification_status()[1]


def test_exact_gamelet_keys_reject_missing_and_extra(tmp_path):
    fixture = _fixture(tmp_path)
    fixture[1][7] = fixture[1].pop(6)
    app = ReplayApp()
    assert _load(app, fixture) is False
    assert "exact gamelet keys" in app.verification_status()[1]


def test_missing_signed_root_is_rejected_even_with_valid_signatures(tmp_path):
    fixture = _fixture(tmp_path)
    data = json.loads(fixture[0].read_text(encoding="utf-8"))
    data["agreement"]["gamelet_outcomes"][0]["final_state_root"] = ""
    fixture[0].write_text(json.dumps(data), encoding="utf-8")
    _resign(fixture[0], fixture[4])
    app = ReplayApp()
    assert _load(app, fixture) is False
    assert "final state root" in app.verification_status()[1]


def test_tampered_private_transition_is_rejected(tmp_path):
    fixture = _fixture(tmp_path)
    journal = Path(fixture[1][1])
    data = json.loads(journal.read_text(encoding="utf-8"))
    data["entries"][0]["local_state_hash"] = "0" * 64
    journal.write_text(json.dumps(data), encoding="utf-8")
    app = ReplayApp()
    assert _load(app, fixture) is False
    assert "chain broken" in app.verification_status()[1]


def test_trusted_config_tamper_is_rejected(tmp_path):
    fixture = _fixture(tmp_path)
    data = json.loads(fixture[3].read_text(encoding="utf-8"))
    data["world"]["hint_max_words"] += 1
    fixture[3].write_text(json.dumps(data), encoding="utf-8")
    app = ReplayApp()
    assert _load(app, fixture) is False
    assert "trusted config" in app.verification_status()[1]


def test_navigation_exposes_reconstructed_state(tmp_path):
    app = ReplayApp()
    assert _load(app, _fixture(tmp_path))
    assert app.last().canonical_state["turn"] == 6
    assert app.last().canonical_state["cop_position"] == [3, 3]
    assert app.first().canonical_state["turn"] == 1
    assert app.next().step == 1
    assert app.prev().step == 0
