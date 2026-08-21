"""Canonical JSON, commitment construction, and derived identifiers."""

from __future__ import annotations

import hashlib
import json
import uuid

from cop_worker.protocol.reference_v3.constants import ReferenceV3Error


def canonical_json(value: object) -> str:
    """The kit's CORE canonical form: compact, sorted, native UTF-8 text."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def reference_commit(payload: dict, nonce: str) -> str:
    """SHA256(canonical_json(payload) + ``|`` + nonce), exactly as the kit vectors pin."""
    if not isinstance(payload, dict) or not isinstance(nonce, str) or not nonce:
        raise ReferenceV3Error("a reference-v3 commit requires a dict payload and non-empty nonce")
    return hashlib.sha256(f"{canonical_json(payload)}|{nonce}".encode()).hexdigest()


def terms_signature(terms: dict, nonce: str) -> str:
    return reference_commit(terms, nonce)


def derive_game_id(group_a: str, group_b: str, label: str | None = None) -> str:
    base = "-vs-".join(sorted((group_a, group_b)))
    return f"{base}-{label}" if label else base


def derive_game_uid(terms: dict, group_a: str, group_b: str, label: str | None = None) -> str:
    """Kit §5 seed: unlabeled uses the sorted pair; a series label folds the
    labeled game_id instead, so two counted series between the same teams
    cannot collapse to one uid (bestteam same-scoreline collision lesson)."""
    pair = "|".join(sorted((group_a, group_b)))
    seed_tail = derive_game_id(group_a, group_b, label) if label else pair
    digest = hashlib.sha256(f"{canonical_json(terms)}|{seed_tail}".encode()).digest()
    return str(uuid.UUID(bytes=digest[:16]))
