"""Validate Step-0 declarations for counted-mode safety."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.step0.declaration import PeerDeclaration

PLACEHOLDER_SHAS: frozenset[str] = frozenset({"placeholder", "unknown", ""})
PLACEHOLDER_GROUP_IDS: frozenset[str] = frozenset({"", "placeholder", "XXXXXXXX"})


def validate_for_counted_mode(decl: PeerDeclaration) -> list[str]:
    """Return list of error strings. Empty list means valid for counted mode.

    A declaration is valid for counted mode only when all identity and
    integrity fields contain real (non-placeholder) values.
    """
    errors: list[str] = []

    if decl.git_sha in PLACEHOLDER_SHAS:
        errors.append("git_sha is placeholder/unknown — counted mode forbidden")

    if len(decl.group_id) != 8:
        errors.append(f"group_id must be 8 chars, got {len(decl.group_id)!r}")

    if decl.group_id in PLACEHOLDER_GROUP_IDS:
        errors.append("group_id is placeholder — counted mode forbidden")

    if decl.model_sha256 in PLACEHOLDER_SHAS:
        errors.append("model_sha256 is placeholder — counted mode forbidden")

    if not decl.canonical_config_sha256:
        errors.append("canonical_config_sha256 missing")

    if not decl.scent_model_hash:
        errors.append("scent_model_hash missing")

    return errors
