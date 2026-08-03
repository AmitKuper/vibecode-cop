"""Durable recovery state for process restart."""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class RecoveryState:
    """All state needed to resume after a crash."""

    game_uid: str
    session_id: str
    role: str
    sm_state: str
    expected_step: int
    last_accepted_commit_step: int
    transcript_root: str
    idempotency_journal: dict  # key -> value cache
    pending_request_id: str
    local_commitments: dict  # step -> h_commit
    local_nonces: dict  # step -> nonce (SECRET — never log)
    report_delivered: bool
    timestamp_utc: str
    schema_version: str = "1.0"

    def canonical_bytes(self) -> bytes:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()


class RecoveryStore:
    def __init__(self, path: str):
        self._path = Path(path)

    def save(self, state: RecoveryState) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(self._path) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(asdict(state), f, indent=2)
        os.replace(tmp, str(self._path))

    def load(self) -> RecoveryState | None:
        if not self._path.exists():
            return None
        with open(self._path) as f:
            return RecoveryState(**json.load(f))

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()
