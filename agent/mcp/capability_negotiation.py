"""Capability document exchange during Step-0."""

import hashlib
import json
from dataclasses import asdict, dataclass, field

DEFAULT_TOOL_MAP_INLINE = {
    "start_game": "start_game",
    "commit": "action",
    "reveal": "action",
    "final_audit": "action",
    "audit_summary": "action",
    "result_agreement": "action",
    "game_end": "action",
    "abort": "action",
}


@dataclass
class CapabilityDocument:
    """Versioned capability document — exchanged during Step-0."""

    schema_version: str = "1.0"
    mcp_transport: str = "SSE"
    mcp_version: str = "1.0"
    tool_names: dict = field(default_factory=lambda: dict(DEFAULT_TOOL_MAP_INLINE))
    supported_phases: list = field(
        default_factory=lambda: [
            "start_game",
            "commit",
            "reveal",
            "final_audit",
            "audit_summary",
            "result_agreement",
            "game_end",
            "abort",
        ]
    )
    signature_algorithms: list = field(default_factory=lambda: ["Ed25519"])
    canonicalization: str = "json_sort_keys"
    idempotency_behavior: str = "full_content_key"
    commitment_payload_semantics: str = "sha256_move_hint_intent_state_hash"
    extensions: list = field(default_factory=list)

    def canonical_bytes(self) -> bytes:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()

    def capability_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class CapabilityNegotiationError(ValueError):
    pass


def validate_compatibility(local: CapabilityDocument, remote: CapabilityDocument) -> None:
    """Raise CapabilityNegotiationError if incompatible.

    Checks required fields before Step-0 locks.
    """
    if local.signature_algorithms != remote.signature_algorithms:
        raise CapabilityNegotiationError(
            f"Signature algorithm mismatch: local={local.signature_algorithms} "
            f"remote={remote.signature_algorithms}"
        )
    if local.canonicalization != remote.canonicalization:
        raise CapabilityNegotiationError(
            f"Canonicalization mismatch: {local.canonicalization} vs {remote.canonicalization}"
        )
    if local.commitment_payload_semantics != remote.commitment_payload_semantics:
        raise CapabilityNegotiationError(
            f"Commitment semantics mismatch: {local.commitment_payload_semantics} "
            f"vs {remote.commitment_payload_semantics}"
        )
    # All required phases must be supported by both
    required = {"commit", "reveal", "final_audit", "start_game"}
    missing_remote = required - set(remote.supported_phases)
    if missing_remote:
        raise CapabilityNegotiationError(f"Remote missing required phases: {missing_remote}")
