"""Local signed append-only league ledger.

Enforces:
- At most MAX_COUNTED_MATCHES counted matches total.
- Each opponent may appear in at most one counted match.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

MAX_COUNTED_MATCHES: int = 10
MIN_DIFFERENT_GROUPS: int = 2


@dataclass
class LedgerEntry:
    """A single match record in the league ledger."""

    opponent_id: str
    match_id: str
    counted: bool
    declaration_hash: str
    result_hash: str
    timestamp_utc: str
    both_result_signatures: list[str] = field(default_factory=list)
    report_delivery_ids: list[str] = field(default_factory=list)
    previous_entry_hash: str = ""

    def canonical_bytes(self) -> bytes:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()

    def entry_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class LeagueLedgerError(ValueError):
    """Raised when a ledger constraint is violated."""


class LeagueLedger:
    """Append-only ledger. Raises LeagueLedgerError on constraint violations.

    The ledger is persisted as a JSON file at the given path.
    Each entry links to the previous entry's hash, forming a chain.
    """

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._entries: list[LedgerEntry] = []
        if self._path.exists():
            self._load()

    def _load(self) -> None:
        with open(self._path) as f:
            data = json.load(f)
        self._entries = [LedgerEntry(**e) for e in data.get("entries", [])]

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump({"entries": [asdict(e) for e in self._entries]}, f, indent=2)

    def counted_opponents(self) -> set[str]:
        """Return the set of opponent IDs that appear in counted matches."""
        return {e.opponent_id for e in self._entries if e.counted}

    def counted_match_count(self) -> int:
        """Return the total number of counted matches recorded."""
        return sum(1 for e in self._entries if e.counted)

    def ledger_root(self) -> str:
        """Return the hash of the latest entry, or a sentinel for empty ledger."""
        if not self._entries:
            return hashlib.sha256(b"empty").hexdigest()
        return self._entries[-1].entry_hash()

    def validate_before_append(self, opponent_id: str, counted: bool) -> None:
        """Raise LeagueLedgerError if the new entry would violate constraints."""
        if not counted:
            return
        if opponent_id in self.counted_opponents():
            raise LeagueLedgerError(f"Already played counted match against {opponent_id!r}")
        if self.counted_match_count() >= MAX_COUNTED_MATCHES:
            raise LeagueLedgerError(f"Max counted matches ({MAX_COUNTED_MATCHES}) reached")

    def append(self, entry: LedgerEntry) -> None:
        """Validate and append *entry*, then persist to disk."""
        self.validate_before_append(entry.opponent_id, entry.counted)
        entry.previous_entry_hash = self.ledger_root()
        self._entries.append(entry)
        self._save()

    def has_minimum_different_groups(self) -> bool:
        """Return True if at least MIN_DIFFERENT_GROUPS distinct opponents recorded."""
        return len(self.counted_opponents()) >= MIN_DIFFERENT_GROUPS
