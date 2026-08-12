"""Commit-reveal step-loop helper for the Step-0-anchored replay fixtures."""

from __future__ import annotations

from cop_worker.audit.step_journal import StepEvidence
from cop_worker.crypto import (
    build_private_state_commitment,
    build_public_transition_root,
    canonical_domain_state_root,
    create_commitment,
)
from cop_worker.domain.transition import apply_joint_action

_MOVES = ["E", "E", "E", "S", "S", "S"]
_ALIASES = {"E": "EAST", "S": "SOUTH"}


def _run_gamelet(
    journal, state, config, *, game_id, gamelet, agreement_hash, config_hash, protocol_hash
):
    """Play the fixed six-move gamelet, appending step evidence to the journal.

    Returns the final domain state and the last public transition root.
    """
    public_root = ""
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
            game_id, step, "cop", cop_state, cop_move, "cop hint", "truth", gamelet, cop_nonce
        )
        thief_commit, _ = create_commitment(
            game_id, step, "thief", thief_state, thief_move, "thief hint", "truth", gamelet,
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
            agreement_hash,
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
    return state, public_root
