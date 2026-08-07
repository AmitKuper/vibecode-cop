"""Bilateral audit summary signed by each peer independently."""

import hashlib
import json
from dataclasses import asdict, dataclass, field

from cop_worker.step0.signing import sign, verify


@dataclass
class AuditSummary:
    game_uid: str
    gamelet: int
    schema_version: str = "2.0"
    transcript_root: str = ""
    declaration_hash: str = ""
    declaration_agreement_hash: str = ""
    config_hash: str = ""
    protocol_profile_hash: str = ""
    public_transition_root: str = ""
    authoritative_final_step: int = 0
    expected_steps: int = 0
    verified_steps: int = 0
    # "PASSED" | "FAILED" | "NOT_APPLICABLE" (zero-turn abort)
    audit_status: str = "NOT_APPLICABLE"
    mismatch_evidence: str = ""
    offending_role: str = ""
    local_final_state_hash: str = ""
    final_state_root: str = ""
    outcome: str = ""
    cop_score: int = 0
    thief_score: int = 0
    token_totals: dict = field(default_factory=dict)
    timestamp_utc: str = ""
    signing_key_id: str = ""
    public_key_hex: str = ""

    def canonical_bytes(self) -> bytes:
        d = asdict(self)
        d.pop("signature_hex", None)
        return json.dumps(d, sort_keys=True, separators=(",", ":")).encode()

    def summary_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def consensus_fields_hash(self) -> str:
        """Hash every field that both isolated peers must independently agree."""
        consensus = {
            "game_uid": self.game_uid,
            "gamelet": self.gamelet,
            "declaration_agreement_hash": self.declaration_agreement_hash,
            "config_hash": self.config_hash,
            "protocol_profile_hash": self.protocol_profile_hash,
            "public_transition_root": self.public_transition_root,
            "authoritative_final_step": self.authoritative_final_step,
            "expected_steps": self.expected_steps,
            "verified_steps": self.verified_steps,
            "audit_status": self.audit_status,
            "final_state_root": self.final_state_root,
            "outcome": self.outcome,
            "cop_score": self.cop_score,
            "thief_score": self.thief_score,
            "token_totals": self.token_totals,
        }
        payload = json.dumps(consensus, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(payload).hexdigest()


@dataclass
class SignedAuditSummary:
    summary: AuditSummary
    signature_hex: str

    def to_dict(self) -> dict:
        return {"summary": asdict(self.summary), "signature_hex": self.signature_hex}

    @classmethod
    def from_dict(cls, d: dict) -> "SignedAuditSummary":
        return cls(AuditSummary(**d["summary"]), d["signature_hex"])


def create_signed_audit_summary(
    summary: AuditSummary, private_key_bytes: bytes
) -> SignedAuditSummary:
    sig = sign(private_key_bytes, summary.canonical_bytes())
    return SignedAuditSummary(summary, sig.hex())


def verify_audit_summary(
    signed: SignedAuditSummary, expected_public_key: bytes | None = None
) -> bool:
    pub_bytes = bytes.fromhex(signed.summary.public_key_hex)
    if expected_public_key is not None and pub_bytes != expected_public_key:
        return False
    sig_bytes = bytes.fromhex(signed.signature_hex)
    return verify(pub_bytes, signed.summary.canonical_bytes(), sig_bytes)
