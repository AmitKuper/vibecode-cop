"""Bilateral audit summary signed by each peer independently."""
import hashlib
import json
from dataclasses import asdict, dataclass, field

from agent.step0.signing import sign, verify


@dataclass
class AuditSummary:
    game_uid: str
    gamelet: int
    schema_version: str = "1.0"
    transcript_root: str = ""
    declaration_hash: str = ""
    config_hash: str = ""
    expected_steps: int = 0
    verified_steps: int = 0
    # "PASSED" | "FAILED" | "NOT_APPLICABLE" (zero-turn abort)
    audit_status: str = "NOT_APPLICABLE"
    mismatch_evidence: str = ""
    offending_role: str = ""
    local_final_state_hash: str = ""
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


def verify_audit_summary(signed: SignedAuditSummary) -> bool:
    pub_bytes = bytes.fromhex(signed.summary.public_key_hex)
    sig_bytes = bytes.fromhex(signed.signature_hex)
    return verify(pub_bytes, signed.summary.canonical_bytes(), sig_bytes)
