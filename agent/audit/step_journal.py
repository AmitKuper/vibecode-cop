"""Durable per-step evidence with atomic append."""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from agent.reliability.durable_io import atomic_write_json


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


class StepJournal:
    """Append-only per-game evidence store with hash chain."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._entries: list[StepEvidence] = []
        self._chain_hashes: list[str] = []
        self._genesis_hash = hashlib.sha256(b"genesis").hexdigest()
        if self._path.exists():
            self._load()

    def _load(self) -> None:
        with open(self._path) as f:
            data = json.load(f)
        for item in data.get("entries", []):
            self._entries.append(StepEvidence(**item))
        self._chain_hashes = data.get("chain_hashes", [])

    def _save(self) -> None:
        atomic_write_json(
            self._path,
            {
                "entries": [asdict(e) for e in self._entries],
                "chain_hashes": self._chain_hashes,
            },
        )

    def prev_hash(self) -> str:
        return self._chain_hashes[-1] if self._chain_hashes else self._genesis_hash

    def append(self, evidence: StepEvidence) -> str:
        expected_step = len(self._entries) + 1
        if evidence.step != expected_step:
            raise ValueError(
                f"journal step must be contiguous: expected {expected_step}, got {evidence.step}"
            )
        if evidence.step < 1 or evidence.gamelet < 0:
            raise ValueError("journal steps are one-based and gamelet cannot be negative")
        if evidence.role not in {"cop", "thief"}:
            raise ValueError(f"invalid journal role {evidence.role!r}")
        if self._entries:
            first = self._entries[0]
            if (evidence.game_uid, evidence.gamelet, evidence.role) != (
                first.game_uid,
                first.gamelet,
                first.role,
            ):
                raise ValueError("journal identity changed within one gamelet")
        h = evidence.event_hash(self.prev_hash())
        evidence.transcript_hash = h
        self._chain_hashes.append(h)
        self._entries.append(evidence)
        self._save()
        return h

    def transcript_root(self) -> str:
        return self._chain_hashes[-1] if self._chain_hashes else self._genesis_hash

    def verify_chain(self, expected_steps: int | None = None) -> tuple[bool, str]:
        """Verify entire chain. Returns (ok, error_msg)."""
        if len(self._entries) != len(self._chain_hashes):
            return (
                False,
                f"journal corrupted: {len(self._entries)} entries but "
                f"{len(self._chain_hashes)} chain hashes",
            )
        prev = self._genesis_hash
        for i, (entry, stored_hash) in enumerate(
            zip(self._entries, self._chain_hashes, strict=True)
        ):
            expected_step = i + 1
            if entry.step != expected_step:
                return False, f"journal step mismatch: expected {expected_step}, got {entry.step}"
            if i and (
                entry.game_uid,
                entry.gamelet,
                entry.role,
            ) != (
                self._entries[0].game_uid,
                self._entries[0].gamelet,
                self._entries[0].role,
            ):
                return False, f"journal identity mismatch at step {entry.step}"
            computed = entry.event_hash(prev)
            if computed != stored_hash:
                return (
                    False,
                    f"Chain broken at step {i}: computed={computed} stored={stored_hash}",
                )
            if entry.transcript_hash and entry.transcript_hash != stored_hash:
                return False, f"entry transcript hash mismatch at step {entry.step}"
            prev = stored_hash
        if expected_steps is not None and len(self._entries) != expected_steps:
            return False, f"expected {expected_steps} journal steps, got {len(self._entries)}"
        return True, ""

    def seal_nonces(
        self,
        local_nonces: dict[int, str],
        received_nonces: dict[int, str],
        *,
        expected_steps: int,
    ) -> str:
        """Seal final-audit nonces and rebuild the hash chain exactly once."""
        expected = set(range(1, expected_steps + 1))
        if set(local_nonces) != expected or set(received_nonces) != expected:
            raise ValueError("nonce sets must exactly match authoritative journal steps")
        if len(self._entries) != expected_steps:
            raise ValueError("journal extent does not match authoritative final step")
        self._chain_hashes = []
        for entry in self._entries:
            entry.local_nonce = local_nonces[entry.step]
            entry.received_nonce = received_nonces[entry.step]
            entry.transcript_hash = ""
            digest = entry.event_hash(self.prev_hash())
            entry.transcript_hash = digest
            self._chain_hashes.append(digest)
        self._save()
        return self.transcript_root()

    @property
    def entries(self) -> list[StepEvidence]:
        return list(self._entries)
