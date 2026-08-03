"""Durable per-step evidence with atomic append."""

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


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
    received_state_hash: str = ""
    received_reveal_sig: str = ""
    reveal_ack_digest: str = ""

    # Verification
    commitment_verified: bool = False
    transcript_hash: str = ""  # chain: SHA256(prev || canonical_event_bytes)
    protocol_state_before: str = ""
    protocol_state_after: str = ""
    timestamp_utc: str = ""

    def canonical_bytes(self) -> bytes:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()

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
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(self._path) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(
                {
                    "entries": [asdict(e) for e in self._entries],
                    "chain_hashes": self._chain_hashes,
                },
                f,
                indent=2,
            )
        os.replace(tmp, str(self._path))  # atomic

    def prev_hash(self) -> str:
        return self._chain_hashes[-1] if self._chain_hashes else self._genesis_hash

    def append(self, evidence: StepEvidence) -> str:
        h = evidence.event_hash(self.prev_hash())
        self._chain_hashes.append(h)
        self._entries.append(evidence)
        self._save()
        return h

    def transcript_root(self) -> str:
        return self._chain_hashes[-1] if self._chain_hashes else self._genesis_hash

    def verify_chain(self) -> tuple[bool, str]:
        """Verify entire chain. Returns (ok, error_msg)."""
        prev = self._genesis_hash
        for i, (entry, stored_hash) in enumerate(
            zip(self._entries, self._chain_hashes, strict=False)
        ):
            computed = entry.event_hash(prev)
            if computed != stored_hash:
                return (
                    False,
                    f"Chain broken at step {i}: computed={computed} stored={stored_hash}",
                )
            prev = stored_hash
        return True, ""

    @property
    def entries(self) -> list[StepEvidence]:
        return list(self._entries)
