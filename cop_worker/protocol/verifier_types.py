"""Verifier result type and canonical field tables."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


_NONCE_FIELDS = frozenset(["nonce", "nonces"])
_COMMITMENT_FIELDS = frozenset(["commitment", "commit", "h_commit"])


@dataclass
class VerificationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def reject_reason(self) -> str:
        return "; ".join(self.errors) if self.errors else ""


#: Semantic payload each security-critical phase must carry (or a signed envelope).
_REQUIRED_BY_PHASE = {
    "start_game": {"game_id", "gamelet", "role", "signature"},
    "commit": {"game_id", "step", "role", "commitment", "signature"},
    "reveal": {"game_id", "step", "role", "move", "signature"},
    "final_audit": {"game_id", "role", "nonces", "signature"},
    "audit_summary": {"game_id", "role", "signed_audit_summary", "signature"},
    "game_end": {"game_id", "role", "reason", "signature"},
    "result_agreement": {"game_id", "role", "signed_agreement", "signature"},
    "abort": {"game_id", "role", "reason", "signature"},
}
