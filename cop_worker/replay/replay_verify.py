"""Replay verification: step-0 anchoring, signatures, actor checks (mixin)."""

from __future__ import annotations

import json

from cop_worker.audit.result_consensus import ResultAgreement
from cop_worker.audit.step_journal import StepEvidence
from cop_worker.crypto import (
    build_private_state_commitment,
    verify_commitment,
)
from cop_worker.domain.types import DomainState
from cop_worker.replay.replay_types import ReplayError
from cop_worker.step0.declaration import SignedDeclaration
from cop_worker.step0.signing import verify as verify_signature


class ReplayVerifyMixin:
    """Cryptographic verification helpers for replay loading."""

    @staticmethod
    def _read_json(path: str) -> dict:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ReplayError(f"{path} must contain a JSON object")
        return value

    @staticmethod
    def _verified_step0(path: str) -> tuple[SignedDeclaration, SignedDeclaration, dict]:
        evidence = ReplayVerifyMixin._read_json(path)
        local = SignedDeclaration.from_dict(evidence["local_signed_declaration"])
        remote = SignedDeclaration.from_dict(evidence["remote_signed_declaration"])
        for label, signed in (("local", local), ("remote", remote)):
            public = bytes.fromhex(signed.declaration.public_key_hex)
            signature = bytes.fromhex(signed.signature_hex)
            if len(public) != 32 or not verify_signature(
                public, signed.declaration.canonical_bytes(), signature
            ):
                raise ReplayError(f"{label} Step-0 signature is invalid")
        agreement = evidence["declaration_agreement"]
        hashes = sorted(
            [local.declaration.declaration_hash(), remote.declaration.declaration_hash()]
        )
        import hashlib

        expected = hashlib.sha256("".join(hashes).encode()).hexdigest()
        if agreement.get("agreement_hash") != expected:
            raise ReplayError("Step-0 declaration agreement hash is invalid")
        if {
            agreement.get("local_declaration_hash"),
            agreement.get("remote_declaration_hash"),
        } != set(hashes):
            raise ReplayError("Step-0 declaration hashes do not match signed declarations")
        return local, remote, agreement

    @staticmethod
    def _verify_result_signatures(
        agreement: ResultAgreement,
        artifact: dict,
        declarations: tuple[SignedDeclaration, SignedDeclaration],
    ) -> None:
        signatures = [artifact.get("local_signature_hex"), artifact.get("remote_signature_hex")]
        if any(not isinstance(value, str) or not value for value in signatures):
            raise ReplayError("counted result requires both bilateral signatures")
        keys = [bytes.fromhex(item.declaration.public_key_hex) for item in declarations]
        valid_assignments = (
            all(
                verify_signature(key, agreement.canonical_bytes(), bytes.fromhex(signature))
                for key, signature in zip(keys, signatures, strict=True)
            ),
            all(
                verify_signature(key, agreement.canonical_bytes(), bytes.fromhex(signature))
                for key, signature in zip(reversed(keys), signatures, strict=True)
            ),
        )
        if not any(valid_assignments):
            raise ReplayError("bilateral result signatures are not anchored in trusted Step-0 keys")

    @staticmethod
    def _actor_fields(entry: StepEvidence) -> tuple[dict, dict]:
        local = {
            "role": entry.role,
            "commitment": entry.local_commitment,
            "nonce": entry.local_nonce,
            "move": entry.local_move,
            "hint": entry.local_hint,
            "intent": entry.local_intent,
            "state_hash": entry.local_state_hash,
        }
        received = {
            "role": "thief" if entry.role == "cop" else "cop",
            "commitment": entry.received_commitment,
            "nonce": entry.received_nonce,
            "move": entry.received_move,
            "hint": entry.received_hint,
            "intent": entry.received_intent,
            "state_hash": entry.received_state_hash,
        }
        return local, received

    @staticmethod
    def _verify_actor(actor: dict, state: DomainState, game_id: str, gamelet: int, step: int):
        role = actor["role"]
        own_position = state.cop_position if role == "cop" else state.thief_position
        own_barriers = state.cop_barriers_remaining if role == "cop" else 0
        expected_state = build_private_state_commitment(
            own_position=own_position,
            own_barriers_remaining=own_barriers,
            local_nonce=actor["nonce"],
            step=step,
            gamelet=gamelet,
            game_uid=game_id,
        )
        if actor["state_hash"] != expected_state:
            raise ReplayError(f"step {step} {role} private state commitment mismatch")
        if not verify_commitment(
            h_commit=actor["commitment"],
            game_id=game_id,
            gamelet=gamelet,
            step=step,
            role=role,
            state_hash=actor["state_hash"],
            move=actor["move"],
            hint=actor["hint"],
            intent=actor["intent"],
            nonce=actor["nonce"],
        ):
            raise ReplayError(f"step {step} {role} commitment mismatch")
