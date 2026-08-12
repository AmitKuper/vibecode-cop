"""Six-gamelet signed replay fixture builders for the ported replay-app tests."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from cop_worker.audit.result_consensus import GameletOutcome, ResultAgreement
from cop_worker.audit.step_journal import StepJournal
from cop_worker.config.shared_config import config_sha256
from cop_worker.crypto import canonical_domain_state_root, combined_protocol_hash
from cop_worker.domain.config_validator import game_config_from_dict
from cop_worker.domain.types import DomainState
from cop_worker.replay.replay_app import ReplayApp
from cop_worker.step0.declaration import DeclarationAgreement, PeerDeclaration, SignedDeclaration
from cop_worker.step0.signing import generate_key_pair, sign
from tests.helpers_replay_steps import _run_gamelet


def _signed_declaration(declaration: PeerDeclaration, private: bytes) -> SignedDeclaration:
    return SignedDeclaration(declaration, sign(private, declaration.canonical_bytes()).hex())


def _fixture(tmp_path: Path):
    from cop_worker.config.shared_config import load_shared_config

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
        journal_path = tmp_path / f"journal_g{gamelet:02d}.json"
        journal = StepJournal(str(journal_path))
        state, public_root = _run_gamelet(
            journal,
            state,
            config,
            game_id=game_id,
            gamelet=gamelet,
            agreement_hash=agreement.agreement_hash,
            config_hash=config_hash,
            protocol_hash=protocol_hash,
        )
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
