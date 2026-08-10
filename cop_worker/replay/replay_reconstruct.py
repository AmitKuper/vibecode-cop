"""Replay gamelet reconstruction from the canonical step journal (mixin)."""

from __future__ import annotations

from cop_worker.audit.result_consensus import GameletOutcome
from cop_worker.audit.step_journal import StepJournal
from cop_worker.crypto import (
    build_public_transition_root,
    canonical_domain_state_root,
    combined_protocol_hash,
)
from cop_worker.domain.transition import apply_joint_action
from cop_worker.domain.types import DomainState
from cop_worker.replay.replay_types import ReplayError
from cop_worker.step0.declaration import SignedDeclaration


class ReplayReconstructMixin:
    """Deterministic re-derivation of every intermediate state."""

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
