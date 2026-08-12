"""Step-0: profile, negotiation payload construction and verification."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from cop_worker.protocol.introspector import IntrospectionResult
from cop_worker.protocol.reference_v3.constants import (
    REFERENCE_V3_DIALECT,
    REFERENCE_V3_SCENT_LOCK,
    REFERENCE_V3_WIRE_LOCK,
    SCENT_LOCKS,
    TERMS_KEYS,
    ReferenceV3Error,
)
from cop_worker.protocol.reference_v3.hashing import (
    canonical_hash,
    derive_game_id,
    derive_game_uid,
    terms_signature,
)
from cop_worker.protocol.reference_v3.terms import is_reference_v3_surface


@dataclass(frozen=True)
class ReferenceV3Profile:
    schema_digest: str
    server_name: str
    dialect: str = REFERENCE_V3_DIALECT
    wire_lock_sha256: str = REFERENCE_V3_WIRE_LOCK
    scent_lock_sha256: str = REFERENCE_V3_SCENT_LOCK
    profile_hash: str = ""

    @classmethod
    def from_introspection(cls, intro: IntrospectionResult) -> ReferenceV3Profile:
        if not is_reference_v3_surface(intro):
            raise ReferenceV3Error("remote MCP surface is not reference-v3")
        fields = {
            "schema_digest": intro.schema_digest,
            "server_name": intro.server_name,
            "dialect": REFERENCE_V3_DIALECT,
            "wire_lock_sha256": REFERENCE_V3_WIRE_LOCK,
            "scent_lock_sha256": REFERENCE_V3_SCENT_LOCK,
        }
        return cls(**fields, profile_hash=canonical_hash(fields))

    def verify(self, schema_digest: str) -> bool:
        fields = asdict(self)
        claimed = fields.pop("profile_hash")
        return schema_digest == self.schema_digest and claimed == canonical_hash(fields)


@dataclass(frozen=True)
class NegotiatedReferenceV3:
    game_id: str
    game_uid: str
    opponent_group: str
    opponent_role: str | None
    terms: dict


def build_negotiation(
    *,
    terms: dict,
    nonce: str,
    group_id: str,
    group_name: str,
    role: str,
    sub_game_number: int,
    opponent_group: str | None = None,
    identity: dict | None = None,
    scent_model: str = "multiplicative_book_v1",
) -> dict:
    if role not in {"police", "thief"} or sub_game_number not in range(1, 7):
        raise ReferenceV3Error("reference-v3 requires police/thief and sub-game 1..6")
    if scent_model not in SCENT_LOCKS:
        raise ReferenceV3Error(
            f"unknown scent model {scent_model!r}; registered: {sorted(SCENT_LOCKS)}"
        )
    # Identity is what the peer records about us (rules 49/53): repos, github_commit,
    # counted count, members. Callers should pass a full identity; the default is empty.
    default_identity = {
        "group_id": group_id,
        "group_name": group_name,
        "llm_model": "none (template hints; pure-Python algorithmic movement)",
        "mcp_servers": {},
        "repos": {},
        "members": [],
    }
    wire = {
        "terms": terms,
        "nonce": nonce,
        "signature": terms_signature(terms, nonce),
        "group_id": group_id,
        "role": role,
        "sub_game_number": sub_game_number,
        "identity": identity or default_identity,
        "scent_model_sha256": SCENT_LOCKS[scent_model],
        "wire_shape_sha256": REFERENCE_V3_WIRE_LOCK,
    }
    if opponent_group:
        wire["game_uid"] = derive_game_uid(terms, group_id, opponent_group)
    return wire


def verify_negotiation(ours: dict, theirs: dict) -> NegotiatedReferenceV3:
    if not isinstance(theirs, dict) or not isinstance(theirs.get("terms"), dict):
        raise ReferenceV3Error("SPAR-N01: peer did not send flat signed terms")
    terms = theirs["terms"]
    missing = set(TERMS_KEYS) - set(terms)
    if missing or set(terms) != set(TERMS_KEYS):
        raise ReferenceV3Error(f"SPAR-N02: incomplete or extended terms: {sorted(missing)}")
    if terms != ours["terms"]:
        raise ReferenceV3Error("SPAR-N03: negotiated terms differ")
    nonce = theirs.get("nonce")
    signature = theirs.get("signature")
    if not isinstance(nonce, str) or terms_signature(terms, nonce) != signature:
        raise ReferenceV3Error("SPAR-N04: terms signature does not verify")
    for family in ("scent_model_sha256", "wire_shape_sha256"):
        left, right = ours.get(family), theirs.get(family)
        if left is not None and right is not None and left != right:
            raise ReferenceV3Error(f"SPAR-N05: {family} lock mismatch")
    ours_n, theirs_n = ours.get("sub_game_number"), theirs.get("sub_game_number")
    if isinstance(ours_n, int) and isinstance(theirs_n, int) and ours_n != theirs_n:
        raise ReferenceV3Error("SPAR-N06: sub-game mismatch")
    if ours.get("role") == theirs.get("role"):
        raise ReferenceV3Error("SPAR-N07: role collision")
    opponent = theirs.get("group_id") or (theirs.get("identity") or {}).get("group_id")
    if not isinstance(opponent, str) or not opponent:
        raise ReferenceV3Error("SPAR-N08: peer names no group_id")
    uid = derive_game_uid(terms, ours["group_id"], opponent)
    if isinstance(theirs.get("game_uid"), str) and theirs["game_uid"] != uid:
        raise ReferenceV3Error("SPAR-N10: game_uid mismatch")
    return NegotiatedReferenceV3(
        game_id=derive_game_id(ours["group_id"], opponent),
        game_uid=uid,
        opponent_group=opponent,
        opponent_role=theirs.get("role"),
        terms=terms,
    )
