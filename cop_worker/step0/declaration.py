"""Bilateral Step-0 declarations with full provenance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime


@dataclass
class GameletDeclarationFields:
    """Fields added to gamelet declarations per new design.

    Captures the sub-game number, role, and canonical series identity
    needed to trace each gamelet back to its parent series declaration.
    """

    sub_game_number: int
    role: str
    game_uid: str


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class PeerDeclaration:
    """Full provenance declaration exchanged at Step-0 before any gameplay."""

    game_uid: str
    schema_version: str = "1.0"

    # Identity
    team_name: str = ""
    group_id: str = ""  # Eight-character ID — EXTERNAL_PENDING until real
    member_ids: list[str] = field(default_factory=list)
    cop_repo_url: str = ""
    thief_repo_url: str = ""

    # Provenance
    git_sha: str = ""  # Must be real non-placeholder for counted mode
    semantic_version: str = "0.1.0"
    release_tag: str = ""

    # Hardware
    os_info: str = ""
    cpu_info: str = ""
    ram_gb: float = 0.0
    gpu_info: str = ""

    # Model
    model_role: str = ""
    model_algorithm: str = ""
    model_sha256: str = ""  # Must match MANIFEST.json
    model_schema_version: str = "1.0"
    inference_mode: str = "argmax"

    # LLM
    llm_provider: str = ""
    llm_model: str = ""
    llm_token_budget: int = 0

    # Network
    local_endpoint: str = ""
    opponent_endpoint: str = ""
    transport: str = "SSE"
    protocol_version: str = "1.0"
    adapter_mapping_hash: str = ""

    # Config
    config_sha256: str = ""  # Raw bytes SHA
    canonical_config_sha256: str = ""  # CanonicalConfig.config_sha256
    scent_model_hash: str = ""
    scent_numerical_vector: list[float] = field(default_factory=list)

    # Match accounting
    counted_mode: bool = False
    opponent_identity: str = ""
    previous_counted_matches: int = 0
    league_ledger_root: str = ""

    # Timestamps
    timestamp_utc: str = ""

    # Signing
    signing_key_id: str = ""
    public_key_hex: str = ""

    def canonical_bytes(self) -> bytes:
        """Deterministic JSON bytes for signing (excludes signature fields)."""
        d = asdict(self)
        d.pop("signature", None)
        return json.dumps(d, sort_keys=True, separators=(",", ":")).encode()

    def declaration_hash(self) -> str:
        """SHA-256 of the canonical bytes."""
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass
class SignedDeclaration:
    """A PeerDeclaration with its Ed25519 signature."""

    declaration: PeerDeclaration
    signature_hex: str

    def to_dict(self) -> dict:
        return {
            "declaration": asdict(self.declaration),
            "signature_hex": self.signature_hex,
        }

    @classmethod
    def from_dict(cls, d: dict) -> SignedDeclaration:
        return cls(PeerDeclaration(**d["declaration"]), d["signature_hex"])


@dataclass
class DeclarationAgreement:
    """Both sides agreed on the same config and game_uid."""

    game_uid: str
    agreement_hash: str  # SHA-256 of both declaration hashes concatenated (sorted)
    local_declaration_hash: str
    remote_declaration_hash: str
    timestamp_utc: str

    def canonical_bytes(self) -> bytes:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()

    @classmethod
    def from_declarations(
        cls,
        game_uid: str,
        local_hash: str,
        remote_hash: str,
    ) -> DeclarationAgreement:
        """Build an agreement from two declaration hashes."""
        combined = "".join(sorted([local_hash, remote_hash]))
        agreement_hash = hashlib.sha256(combined.encode()).hexdigest()
        return cls(
            game_uid=game_uid,
            agreement_hash=agreement_hash,
            local_declaration_hash=local_hash,
            remote_declaration_hash=remote_hash,
            timestamp_utc=_utc_now(),
        )
