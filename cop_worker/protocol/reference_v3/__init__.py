"""Deterministic compatibility layer for the league kit's ``reference-v3`` wire.

This dialect is intentionally separate from the course-native eight-call protocol.  A
``reference-v3`` half-turn sends one sealed record and defers the move and nonce reveal to the
bilateral audit.  Treating it as a collection of renamed ``commit``/``reveal`` tools would leak
the nonce or send two messages where the peer expects one.

The protocol-understanding agent may select this module only before a game starts.  Gameplay is
then handled by :class:`ReferenceV3Session`; it performs no LLM calls and accepts no secrets or
signing authority from discovery data.
"""

from cop_worker.protocol.reference_v3.constants import (
    REFERENCE_V3_DIALECT,
    REFERENCE_V3_SCENT_LOCK,
    REFERENCE_V3_TOOLS,
    REFERENCE_V3_WIRE_LOCK,
    SCENT_LOCKS,
    TERMS_KEYS,
    ReferenceV3EquivocationError,
    ReferenceV3Error,
)
from cop_worker.protocol.reference_v3.hashing import (
    canonical_hash,
    canonical_json,
    derive_game_id,
    derive_game_uid,
    reference_commit,
    terms_signature,
)
from cop_worker.protocol.reference_v3.negotiation import (
    NegotiatedReferenceV3,
    ReferenceV3Profile,
    build_negotiation,
    verify_negotiation,
)
from cop_worker.protocol.reference_v3.session import ReferenceV3Session, register_reference_v3_tools
from cop_worker.protocol.reference_v3.terms import (
    _FALLBACK_TERMS,
    _base_terms,
    _object_argument,
    default_terms,
    is_reference_v3_surface,
    terms_from_game,
)
from cop_worker.protocol.reference_v3.turns import (
    ReferenceV3Inbox,
    build_turn,
    validate_turn,
    verify_audit,
)
from cop_worker.protocol.reference_v3.vectors import assert_core_vectors

__all__ = [
    "REFERENCE_V3_DIALECT",
    "REFERENCE_V3_SCENT_LOCK",
    "REFERENCE_V3_TOOLS",
    "REFERENCE_V3_WIRE_LOCK",
    "SCENT_LOCKS",
    "TERMS_KEYS",
    "NegotiatedReferenceV3",
    "ReferenceV3EquivocationError",
    "ReferenceV3Error",
    "ReferenceV3Inbox",
    "ReferenceV3Profile",
    "ReferenceV3Session",
    "_FALLBACK_TERMS",
    "_base_terms",
    "_object_argument",
    "assert_core_vectors",
    "build_negotiation",
    "build_turn",
    "canonical_hash",
    "canonical_json",
    "default_terms",
    "derive_game_id",
    "derive_game_uid",
    "is_reference_v3_surface",
    "reference_commit",
    "register_reference_v3_tools",
    "terms_from_game",
    "terms_signature",
    "validate_turn",
    "verify_audit",
    "verify_negotiation",
]
