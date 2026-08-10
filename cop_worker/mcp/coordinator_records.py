"""Idempotency record and content-key helpers for the coordinator."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reveal_content_key(
    move: str,
    hint: str | None = None,
    intent: str | None = None,
    state_hash: str | None = None,
) -> str:
    """Compute a canonical SHA-256 hash over the full reveal payload.

    This ensures idempotency is keyed on all mutable fields, not just move,
    so a replay that alters hint/intent/state_hash is detected as a conflict.
    """
    from cop_worker.crypto import canonical_json

    payload = {
        "move": move,
        "hint": hint or "",
        "intent": intent or "",
        "state_hash": state_hash or "",
    }
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


@dataclass
class _IdempotencyRecord:
    content_key: str  # h_commit for commits, full-payload hash for reveals
    cached_response: dict
