"""Single-step evidence record: canonical bytes and hash."""

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass
class StepEvidence:
    """Evidence for one step in the commit-reveal protocol."""

    game_uid: str
    gamelet: int
    step: int
    role: str  # "cop" or "thief"

    # Commit phase
    local_commitment: str = ""  # h_commit we sent
    local_nonce: str = ""  # our nonce (stays secret until audit)
    local_commitment_sig: str = ""  # our signature on commitment
    received_commitment: str = ""  # opponent's h_commit
    received_commitment_sig: str = ""
    commitment_ack_digest: str = ""  # digest of our ack response

    # Reveal phase
    local_move: str = ""
    local_hint: str = ""
    local_intent: str = ""
    local_state_hash: str = ""
    local_reveal_sig: str = ""
    received_move: str = ""
    received_hint: str = ""
    received_intent: str = ""
    received_state_hash: str = ""
    received_nonce: str = ""  # populated only when final audit seals the journal
    received_reveal_sig: str = ""
    reveal_ack_digest: str = ""

    # Verification
    commitment_verified: bool = False
    transcript_hash: str = ""  # chain: SHA256(prev || canonical_event_bytes)
    protocol_state_before: str = ""
    protocol_state_after: str = ""
    timestamp_utc: str = ""
    public_transition_root: str = ""
    state_before_root: str = ""
    state_after_root: str = ""
    outcome: str = ""
    cop_score: int = 0
    thief_score: int = 0

    def canonical_bytes(self) -> bytes:
        payload = asdict(self)
        payload.pop("transcript_hash", None)
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    def event_hash(self, previous_hash: str) -> str:
        payload = (previous_hash + self.canonical_bytes().decode()).encode()
        return hashlib.sha256(payload).hexdigest()
