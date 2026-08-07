"""Bilateral result agreement — both peers must sign identical consensus."""

import hashlib
import json
from dataclasses import asdict, dataclass, field

from cop_worker.step0.signing import sign, verify


@dataclass
class GameletOutcome:
    gamelet: int
    cop_score: int
    thief_score: int
    winner: str  # "cop" | "thief" | "draw"
    turns_played: int
    technical_loss_role: str = ""  # "" | "cop" | "thief"
    transcript_root: str = ""
    final_state_root: str = ""
    public_transition_root: str = ""
    token_totals: dict = field(default_factory=dict)


@dataclass
class ResultAgreement:
    game_uid: str
    schema_version: str = "1.0"
    gamelet_outcomes: list = field(default_factory=list)  # list[GameletOutcome]
    cop_total_score: int = 0
    thief_total_score: int = 0
    series_winner: str = ""  # "cop" | "thief" | "draw"
    counted_status: bool = False
    token_totals: dict = field(default_factory=dict)
    config_hash: str = ""
    combined_protocol_profile_hash: str = ""
    ledger_update_hash: str = ""
    both_audit_summaries_hash: str = ""  # SHA256(sorted(hash_a, hash_b))
    timestamp_utc: str = ""
    signing_key_id: str = ""
    public_key_hex: str = ""

    def canonical_bytes(self) -> bytes:
        d = asdict(self)
        d.pop("signature_hex", None)
        return json.dumps(d, sort_keys=True, separators=(",", ":")).encode()

    def agreement_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def consensus_fields_hash(self) -> str:
        """Hash of fields that must match between both peers."""
        consensus = {
            "game_uid": self.game_uid,
            "gamelet_outcomes": [
                asdict(o) if hasattr(o, "__dataclass_fields__") else o
                for o in self.gamelet_outcomes
            ],
            "cop_total_score": self.cop_total_score,
            "thief_total_score": self.thief_total_score,
            "series_winner": self.series_winner,
            "counted_status": self.counted_status,
            "token_totals": self.token_totals,
            "config_hash": self.config_hash,
            "combined_protocol_profile_hash": self.combined_protocol_profile_hash,
            "ledger_update_hash": self.ledger_update_hash,
            "both_audit_summaries_hash": self.both_audit_summaries_hash,
        }
        return hashlib.sha256(
            json.dumps(consensus, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass
class SignedResultAgreement:
    agreement: ResultAgreement
    signature_hex: str

    def to_dict(self) -> dict:
        return {"agreement": asdict(self.agreement), "signature_hex": self.signature_hex}

    @classmethod
    def from_dict(cls, d: dict) -> "SignedResultAgreement":
        d2 = dict(d["agreement"])
        d2["gamelet_outcomes"] = [GameletOutcome(**o) for o in d2.get("gamelet_outcomes", [])]
        return cls(ResultAgreement(**d2), d["signature_hex"])


class ResultConsensusError(ValueError):
    pass


def create_signed_result_agreement(
    agreement: ResultAgreement, private_key_bytes: bytes
) -> SignedResultAgreement:
    return SignedResultAgreement(
        agreement=agreement,
        signature_hex=sign(private_key_bytes, agreement.canonical_bytes()).hex(),
    )


def verify_result_agreement_signature(
    signed: SignedResultAgreement, expected_public_key: bytes
) -> bool:
    try:
        signature = bytes.fromhex(signed.signature_hex)
    except ValueError:
        return False
    return verify(expected_public_key, signed.agreement.canonical_bytes(), signature)


def verify_bilateral_consensus(local: SignedResultAgreement, remote: SignedResultAgreement) -> None:
    """Raise ResultConsensusError if the two signed agreements disagree on consensus fields."""
    local_hash = local.agreement.consensus_fields_hash()
    remote_hash = remote.agreement.consensus_fields_hash()
    if local_hash != remote_hash:
        raise ResultConsensusError(
            f"Result consensus mismatch: local={local_hash} remote={remote_hash}"
        )
    if local.agreement.canonical_bytes() != remote.agreement.canonical_bytes():
        raise ResultConsensusError("Result agreements are not byte-identical")
