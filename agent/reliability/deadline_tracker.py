"""Durable per-request deadline records with retry scheduling."""

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from agent.reliability.durable_io import atomic_write_json


@dataclass
class DeadlineRecord:
    request_id: str
    idempotency_key: str
    game_uid: str
    gamelet: int
    step: int
    phase: str  # "commit" | "reveal" | "audit" | "start_game"
    monotonic_start: float
    expiry_monotonic: float
    max_attempts: int
    attempt: int = 0
    min_retry_delay_s: float = 1.0
    jitter_factor: float = 0.2  # up to 20% random jitter
    last_error: str = ""
    terminal_status: str = ""  # "" | "SUCCESS" | "TIMEOUT" | "PERMANENT_FAIL"
    response_digest: str = ""
    timestamp_utc: str = ""

    def is_expired(self) -> bool:
        return time.monotonic() > self.expiry_monotonic

    def is_terminal(self) -> bool:
        return bool(self.terminal_status)

    def next_retry_delay(self) -> float:
        import random

        base = self.min_retry_delay_s * (2**self.attempt)
        jitter = random.uniform(0, self.jitter_factor * base)
        return base + jitter

    def canonical_bytes(self) -> bytes:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()


class DeadlineTracker:
    """Thread-safe tracker for outstanding request deadlines."""

    def __init__(self, storage_path: str, timeout_s: float = 30.0, max_attempts: int = 3):
        self._path = Path(storage_path)
        self._timeout_s = timeout_s
        self._max_attempts = max_attempts
        self._records: dict[str, DeadlineRecord] = {}
        self._lock = threading.Lock()
        if self._path.exists():
            self._load()

    def _load(self) -> None:
        with open(self._path) as f:
            data = json.load(f)
        for r in data.get("records", []):
            rec = DeadlineRecord(**r)
            self._records[rec.request_id] = rec

    def _save(self) -> None:
        atomic_write_json(self._path, {"records": [asdict(r) for r in self._records.values()]})

    def begin(
        self, idempotency_key: str, game_uid: str, gamelet: int, step: int, phase: str
    ) -> DeadlineRecord:
        with self._lock:
            request_id = str(uuid.uuid4())
            now = time.monotonic()
            rec = DeadlineRecord(
                request_id=request_id,
                idempotency_key=idempotency_key,
                game_uid=game_uid,
                gamelet=gamelet,
                step=step,
                phase=phase,
                monotonic_start=now,
                expiry_monotonic=now + self._timeout_s,
                max_attempts=self._max_attempts,
                timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            )
            self._records[request_id] = rec
            self._save()
            return rec

    def complete(self, request_id: str, status: str = "SUCCESS", response_digest: str = "") -> None:
        with self._lock:
            if request_id in self._records:
                self._records[request_id].terminal_status = status
                self._records[request_id].response_digest = response_digest
                self._save()

    def fail(self, request_id: str, error: str) -> bool:
        """Record failure. Returns True if should retry, False if terminal."""
        with self._lock:
            rec = self._records.get(request_id)
            if not rec:
                return False
            rec.attempt += 1
            rec.last_error = error
            if rec.attempt >= rec.max_attempts or rec.is_expired():
                rec.terminal_status = "TIMEOUT" if rec.is_expired() else "PERMANENT_FAIL"
                self._save()
                return False
            self._save()
            return True

    def pending_expired(self) -> list[DeadlineRecord]:
        with self._lock:
            return [r for r in self._records.values() if not r.is_terminal() and r.is_expired()]

    def get(self, request_id: str) -> DeadlineRecord | None:
        return self._records.get(request_id)
