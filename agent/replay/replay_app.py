"""Step-0-anchored canonical replay and tamper verification."""

from __future__ import annotations

import json
from dataclasses import dataclass
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
    verify_commitment,
)
from agent.step0.declaration import SignedDeclaration
from agent.step0.signing import verify as verify_signature

_GAMELETS = set(range(1, 7))


@dataclass
class ReplayState:
    game_uid: str
    gamelet: int
    step: int
    total_steps: int
    event: StepEvidence | None
    verified: bool
    tamper_reason: str
    transcript_verified: bool
    canonical_state: dict | None = None


class ReplayError(ValueError):
    pass


class ReplayApp:
    """Verify trusted identities, evidence, and every configured transition."""

    def __init__(self):
        self._result: ResultAgreement | None = None
        self._journals: dict[int, StepJournal] = {}
        self._states: dict[int, list[DomainState]] = {}
        self._verified = False
        self._tamper_reason = ""
        self._current_gamelet = 1
        self._current_step = 0

    @staticmethod
    def _read_json(path: str) -> dict:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ReplayError(f"{path} must contain a JSON object")
        return value

    @staticmethod
    def _verified_step0(path: str) -> tuple[SignedDeclaration, SignedDeclaration, dict]:
        evidence = ReplayApp._read_json(path)
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

    def _reconstruct_gamelet(
        self,
        gamelet: int,
        journal: StepJournal,
        outcome: GameletOutcome,
        step0: tuple[SignedDeclaration, SignedDeclaration, dict],
        config,
    ) -> list[DomainState]:
        local, remote, declaration_agreement = step0
        game_id = local.declaration.game_uid
        if remote.declaration.game_uid != game_id:
            raise ReplayError(f"gamelet {gamelet} Step-0 game IDs disagree")
        expected_game_id = f"{self._result.game_uid}_g{gamelet:02d}"
        if game_id != expected_game_id:
            raise ReplayError(f"gamelet {gamelet} unexpected game ID {game_id!r}")
        if local.declaration.config_sha256 != self._result.config_hash or (
            remote.declaration.config_sha256 != self._result.config_hash
        ):
            raise ReplayError(f"gamelet {gamelet} Step-0 config hash mismatch")
        profile_hash = combined_protocol_hash(
            local.declaration.adapter_mapping_hash,
            remote.declaration.adapter_mapping_hash,
        )
        if profile_hash != self._result.combined_protocol_profile_hash:
            raise ReplayError(f"gamelet {gamelet} protocol profile binding mismatch")
        ok, error = journal.verify_chain(expected_steps=outcome.turns_played)
        if not ok:
            raise ReplayError(f"gamelet {gamelet} chain broken: {error}")
        if not outcome.transcript_root or journal.transcript_root() != outcome.transcript_root:
            raise ReplayError(f"gamelet {gamelet} transcript root mismatch")

        state = DomainState(
            turn=0,
            grid_size=config.grid_size,
            cop_position=config.cop_start,
            thief_position=config.thief_start,
            barriers=[],
            cop_barriers_remaining=config.max_barriers,
        )
        states = [state]
        public_root = ""
        for entry in journal.entries:
            if entry.game_uid != game_id or entry.gamelet != gamelet:
                raise ReplayError(f"gamelet {gamelet} journal identity mismatch")
            if entry.state_before_root != canonical_domain_state_root(
                state, self._result.config_hash
            ):
                raise ReplayError(f"gamelet {gamelet} step {entry.step} before-state mismatch")
            local_actor, remote_actor = self._actor_fields(entry)
            self._verify_actor(local_actor, state, game_id, gamelet, entry.step)
            self._verify_actor(remote_actor, state, game_id, gamelet, entry.step)
            actors = {local_actor["role"]: local_actor, remote_actor["role"]: remote_actor}
            aliases = {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST"}
            cop_move = aliases.get(actors["cop"]["move"], actors["cop"]["move"])
            thief_move = aliases.get(actors["thief"]["move"], actors["thief"]["move"])
            transition = apply_joint_action(
                state,
                cop_move,
                thief_move,
                config=config,
            )
            if not transition.cop_action_legal or not transition.thief_action_legal:
                raise ReplayError(f"gamelet {gamelet} step {entry.step} contains illegal action")
            expected_public = build_public_transition_root(
                game_uid=game_id,
                gamelet=gamelet,
                step=entry.step,
                declaration_hash=declaration_agreement["agreement_hash"],
                config_hash=self._result.config_hash,
                protocol_hash=profile_hash,
                public_barriers=list(transition.new_state.barriers),
                cop_barriers_quota=transition.new_state.cop_barriers_remaining,
                revealed_cop_move=cop_move,
                revealed_thief_move=thief_move,
                previous_transcript_root=public_root,
                public_outcome=transition.outcome.value,
            )
            if entry.public_transition_root != expected_public:
                raise ReplayError(f"gamelet {gamelet} step {entry.step} public root mismatch")
            if entry.state_after_root != canonical_domain_state_root(
                transition.new_state, self._result.config_hash
            ):
                raise ReplayError(f"gamelet {gamelet} step {entry.step} after-state mismatch")
            if (entry.outcome, entry.cop_score, entry.thief_score) != (
                transition.outcome.value,
                transition.cop_score,
                transition.thief_score,
            ):
                raise ReplayError(f"gamelet {gamelet} step {entry.step} outcome/score mismatch")
            state = transition.new_state
            states.append(state)
            public_root = expected_public

        expected_winner = {"cop_win": "cop", "thief_win": "thief"}.get(journal.entries[-1].outcome)
        if expected_winner != outcome.winner:
            raise ReplayError(f"gamelet {gamelet} winner mismatch")
        if (outcome.cop_score, outcome.thief_score) != (
            journal.entries[-1].cop_score,
            journal.entries[-1].thief_score,
        ):
            raise ReplayError(f"gamelet {gamelet} final score mismatch")
        if not outcome.final_state_root or outcome.final_state_root != canonical_domain_state_root(
            state, self._result.config_hash
        ):
            raise ReplayError(f"gamelet {gamelet} final state root mismatch")
        if not outcome.public_transition_root or outcome.public_transition_root != public_root:
            raise ReplayError(f"gamelet {gamelet} final public root mismatch")
        return states

    def load(
        self,
        result_path: str,
        journal_paths: dict[int, str],
        *,
        trusted_step0_paths: dict[int, str],
        config_path: str,
    ) -> bool:
        """Verify a counted six-gamelet result and reconstruct every transition."""
        self._verified = False
        self._tamper_reason = ""
        self._journals = {}
        self._states = {}
        try:
            artifact = self._read_json(result_path)
            agreement_data = dict(artifact["agreement"])
            agreement_data["gamelet_outcomes"] = [
                GameletOutcome(**item) for item in agreement_data.get("gamelet_outcomes", [])
            ]
            self._result = ResultAgreement(**agreement_data)
            if not self._result.counted_status:
                raise ReplayError("replay artifact is not a counted result")
            if set(journal_paths) != _GAMELETS or set(trusted_step0_paths) != _GAMELETS:
                raise ReplayError("expected exact gamelet keys {1,2,3,4,5,6}")
            outcomes = {item.gamelet: item for item in self._result.gamelet_outcomes}
            if set(outcomes) != _GAMELETS or len(self._result.gamelet_outcomes) != 6:
                raise ReplayError("signed result is not exactly gamelets 1..6")

            raw_config = self._read_json(config_path)
            if (
                not self._result.config_hash
                or config_sha256(raw_config) != self._result.config_hash
            ):
                raise ReplayError("trusted config does not match signed result")
            config = game_config_from_dict(raw_config)
            step0 = {
                gamelet: self._verified_step0(path) for gamelet, path in trusted_step0_paths.items()
            }
            self._verify_result_signatures(
                self._result,
                artifact,
                (step0[6][0], step0[6][1]),
            )
            for gamelet in sorted(_GAMELETS):
                path = Path(journal_paths[gamelet])
                if not path.is_file():
                    raise ReplayError(f"gamelet {gamelet} journal is missing")
                journal = StepJournal(str(path))
                self._states[gamelet] = self._reconstruct_gamelet(
                    gamelet, journal, outcomes[gamelet], step0[gamelet], config
                )
                self._journals[gamelet] = journal

            if sum(item.cop_score for item in outcomes.values()) != self._result.cop_total_score:
                raise ReplayError("cop series total mismatch")
            if (
                sum(item.thief_score for item in outcomes.values())
                != self._result.thief_total_score
            ):
                raise ReplayError("thief series total mismatch")
            expected_series = (
                "cop"
                if self._result.cop_total_score > self._result.thief_total_score
                else "thief"
                if self._result.thief_total_score > self._result.cop_total_score
                else "draw"
            )
            if self._result.series_winner != expected_series:
                raise ReplayError("series winner mismatch")
        except Exception as exc:
            self._tamper_reason = str(exc)
            return False

        self._verified = True
        self._current_gamelet = 1
        self._current_step = 0
        return True

    def verification_status(self) -> tuple[bool, str]:
        return self._verified, self._tamper_reason

    def current_state(self) -> ReplayState:
        journal = self._journals.get(self._current_gamelet)
        entries = journal.entries if journal else []
        event = entries[self._current_step] if 0 <= self._current_step < len(entries) else None
        states = self._states.get(self._current_gamelet, [])
        domain = states[self._current_step + 1] if event is not None and states else None
        return ReplayState(
            game_uid=self._result.game_uid if self._result else "",
            gamelet=self._current_gamelet,
            step=self._current_step,
            total_steps=len(entries),
            event=event,
            verified=self._verified,
            tamper_reason=self._tamper_reason,
            transcript_verified=self._verified,
            canonical_state=domain.model_dump(mode="json") if domain is not None else None,
        )

    def next(self) -> ReplayState:
        journal = self._journals.get(self._current_gamelet)
        if journal and self._current_step < len(journal.entries) - 1:
            self._current_step += 1
        return self.current_state()

    def prev(self) -> ReplayState:
        if self._current_step > 0:
            self._current_step -= 1
        return self.current_state()

    def first(self) -> ReplayState:
        self._current_step = 0
        return self.current_state()

    def last(self) -> ReplayState:
        journal = self._journals.get(self._current_gamelet)
        if journal:
            self._current_step = max(0, len(journal.entries) - 1)
        return self.current_state()
