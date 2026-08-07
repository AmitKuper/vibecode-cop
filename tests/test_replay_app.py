"""Adversarial tests for Step-0-anchored canonical replay."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from agent.audit.result_consensus import GameletOutcome, ResultAgreement
from agent.audit.step_journal import StepEvidence, StepJournal
from agent.config.shared_config import config_sha256
from agent.domain.config_validator import game_config_from_dict
from agent.domain.transition import apply_joint_action
from agent.domain.types import DomainState
from agent.mcp.crypto import (
    build_private_state_commitment,
    build_public_transition_root,
    canonical_domain_state_root,
    combined_protocol_hash,
    create_commitment,
)
from agent.replay.replay_app import ReplayApp
from agent.step0.declaration import DeclarationAgreement, PeerDeclaration, SignedDeclaration
from agent.step0.signing import generate_key_pair, sign

_MOVES = ["E", "E", "E", "S", "S", "S"]
_ALIASES = {"E": "EAST", "S": "SOUTH"}


def _signed_declaration(declaration: PeerDeclaration, private: bytes) -> SignedDeclaration:
    return SignedDeclaration(declaration, sign(private, declaration.canonical_bytes()).hex())


def _fixture(tmp_path: Path):
    from agent.config.shared_config import load_shared_config

    raw_config = load_shared_config()
    config_path = tmp_path / "game.json"
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")
    config_hash = config_sha256(raw_config)
    config = game_config_from_dict(raw_config)
    cop_private, cop_public = generate_key_pair()
    thief_private, thief_public = generate_key_pair()
    cop_profile = "a" * 64
    thief_profile = "b" * 64
    protocol_hash = combined_protocol_hash(cop_profile, thief_profile)
    series_id = "series_replay_fixture"
    journals: dict[int, str] = {}
    step0_paths: dict[int, str] = {}
    outcomes: list[GameletOutcome] = []

    for gamelet in range(1, 7):
        game_id = f"{series_id}_g{gamelet:02d}"
        cop_decl = PeerDeclaration(
            game_uid=game_id,
            counted_mode=True,
            config_sha256=config_hash,
            canonical_config_sha256=config_hash,
            adapter_mapping_hash=cop_profile,
            public_key_hex=cop_public.hex(),
        )
        thief_decl = PeerDeclaration(
            game_uid=game_id,
            counted_mode=True,
            config_sha256=config_hash,
            canonical_config_sha256=config_hash,
            adapter_mapping_hash=thief_profile,
            public_key_hex=thief_public.hex(),
        )
        cop_signed = _signed_declaration(cop_decl, cop_private)
        thief_signed = _signed_declaration(thief_decl, thief_private)
        agreement = DeclarationAgreement.from_declarations(
            game_id, cop_decl.declaration_hash(), thief_decl.declaration_hash()
        )
        step0_path = tmp_path / f"step0_g{gamelet:02d}.json"
        step0_path.write_text(
            json.dumps(
                {
                    "local_signed_declaration": cop_signed.to_dict(),
                    "remote_signed_declaration": thief_signed.to_dict(),
                    "declaration_agreement": asdict(agreement),
                }
            ),
            encoding="utf-8",
        )
        step0_paths[gamelet] = str(step0_path)

        state = DomainState(
            turn=0,
            grid_size=config.grid_size,
            cop_position=config.cop_start,
            thief_position=config.thief_start,
            barriers=[],
            cop_barriers_remaining=config.max_barriers,
        )
        public_root = ""
        journal_path = tmp_path / f"journal_g{gamelet:02d}.json"
        journal = StepJournal(str(journal_path))
        for step, cop_move in enumerate(_MOVES, start=1):
            thief_move = "STAY"
            cop_nonce = (f"c{gamelet:02d}{step:02d}" + "a" * 64)[:64]
            thief_nonce = (f"t{gamelet:02d}{step:02d}" + "b" * 64)[:64]
            cop_state = build_private_state_commitment(
                state.cop_position,
                state.cop_barriers_remaining,
                cop_nonce,
                step,
                gamelet,
                game_id,
            )
            thief_state = build_private_state_commitment(
                state.thief_position, 0, thief_nonce, step, gamelet, game_id
            )
            cop_commit, _ = create_commitment(
                game_id,
                step,
                "cop",
                cop_state,
                cop_move,
                "cop hint",
                "truth",
                gamelet,
                cop_nonce,
            )
            thief_commit, _ = create_commitment(
                game_id,
                step,
                "thief",
                thief_state,
                thief_move,
                "thief hint",
                "truth",
                gamelet,
                thief_nonce,
            )
            before_root = canonical_domain_state_root(state, config_hash)
            transition = apply_joint_action(
                state, _ALIASES.get(cop_move, cop_move), thief_move, config=config
            )
            next_public = build_public_transition_root(
                game_id,
                gamelet,
                step,
                agreement.agreement_hash,
                config_hash,
                protocol_hash,
                list(transition.new_state.barriers),
                transition.new_state.cop_barriers_remaining,
                _ALIASES.get(cop_move, cop_move),
                thief_move,
                public_root,
                transition.outcome.value,
            )
            journal.append(
                StepEvidence(
                    game_uid=game_id,
                    gamelet=gamelet,
                    step=step,
                    role="cop",
                    local_commitment=cop_commit,
                    local_nonce=cop_nonce,
                    received_commitment=thief_commit,
                    received_nonce=thief_nonce,
                    local_move=cop_move,
                    local_hint="cop hint",
                    local_intent="truth",
                    local_state_hash=cop_state,
                    received_move=thief_move,
                    received_hint="thief hint",
                    received_intent="truth",
                    received_state_hash=thief_state,
                    public_transition_root=next_public,
                    state_before_root=before_root,
                    state_after_root=canonical_domain_state_root(transition.new_state, config_hash),
                    outcome=transition.outcome.value,
                    cop_score=transition.cop_score,
                    thief_score=transition.thief_score,
                )
            )
            state = transition.new_state
            public_root = next_public
        journals[gamelet] = str(journal_path)
        outcomes.append(
            GameletOutcome(
                gamelet=gamelet,
                cop_score=20,
                thief_score=5,
                winner="cop",
                turns_played=6,
                transcript_root=journal.transcript_root(),
                final_state_root=canonical_domain_state_root(state, config_hash),
                public_transition_root=public_root,
            )
        )

    agreement = ResultAgreement(
        game_uid=series_id,
        gamelet_outcomes=outcomes,
        cop_total_score=120,
        thief_total_score=30,
        series_winner="cop",
        counted_status=True,
        config_hash=config_hash,
        combined_protocol_profile_hash=protocol_hash,
    )
    artifact = {
        "agreement": asdict(agreement),
        "local_signature_hex": sign(cop_private, agreement.canonical_bytes()).hex(),
        "remote_signature_hex": sign(thief_private, agreement.canonical_bytes()).hex(),
    }
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(artifact), encoding="utf-8")
    return result_path, journals, step0_paths, config_path, (cop_private, thief_private)


def _load(app: ReplayApp, fixture) -> bool:
    result, journals, step0, config, _ = fixture
    return app.load(str(result), journals, trusted_step0_paths=step0, config_path=str(config))


def _resign(path: Path, private_keys: tuple[bytes, bytes]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = dict(data["agreement"])
    raw["gamelet_outcomes"] = [GameletOutcome(**item) for item in raw["gamelet_outcomes"]]
    agreement = ResultAgreement(**raw)
    data["local_signature_hex"] = sign(private_keys[0], agreement.canonical_bytes()).hex()
    data["remote_signature_hex"] = sign(private_keys[1], agreement.canonical_bytes()).hex()
    path.write_text(json.dumps(data), encoding="utf-8")


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
