"""Small fail-closed primitives for mandatory counted-mode evidence."""

from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any


class PersistenceError(OSError):
    """Raised after every bounded durable-write attempt has failed."""


def _sync_directory(path: Path) -> None:
    """Best-effort directory sync; Windows does not expose portable dir fsync."""
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_bytes(
    path: str | Path,
    payload: bytes,
    *,
    attempts: int = 3,
    retry_delay_s: float = 0.01,
) -> None:
    """Write, flush, fsync, replace, and directory-sync with bounded retry."""
    if attempts < 1:
        raise ValueError("attempts must be positive")
    destination = Path(path)
    last_error: OSError | None = None
    for attempt in range(attempts):
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            _sync_directory(destination.parent)
            return
        except OSError as exc:
            last_error = exc
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            if attempt + 1 < attempts and retry_delay_s:
                time.sleep(retry_delay_s)
    raise PersistenceError(f"durable write failed for {destination}: {last_error}") from last_error


def atomic_write_json(path: str | Path, value: Any, *, attempts: int = 3) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True).encode("utf-8")
    atomic_write_bytes(path, payload, attempts=attempts)
