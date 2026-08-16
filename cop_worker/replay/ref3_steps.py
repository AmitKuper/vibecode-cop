"""Per-step verification of a reference-v3 wire log — the shared replay core.

Both replay frontends (the CLI stepper and the web /replay page) consume this
and nothing else, so the terminal verdict and the screenshot can never disagree.

Book ch.7.4-7.5: for every sealed record, recompute
``SHA256(canonical_json(payload) + "|" + nonce)`` and compare to the stored
commitment. One mismatch anywhere poisons the whole match: ``TAMPERED``.

Local truth holds in replay too: entries expose the RECORDED payloads of both
sides (they were revealed at audit time, so nothing here is hidden knowledge),
but no objective board reconstruction is attempted beyond what those payloads
themselves state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cop_worker.protocol.reference_v3.hashing import reference_commit

VERIFIED = "Verified OK"
TAMPERED = "TAMPERED"


@dataclass(frozen=True)
class StepVerdict:
    """One sealed record, re-verified."""

    index: int  # position on the combined timeline
    side: str  # "ours" | "opponent"
    step: int  # protocol step number from the payload (0 = step-0 record)
    payload: dict
    nonce: str
    stored_commit: str
    recomputed_commit: str

    @property
    def ok(self) -> bool:
        return self.recomputed_commit == self.stored_commit

    @property
    def verdict(self) -> str:
        return VERIFIED if self.ok else TAMPERED


def load_log(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def iter_steps(doc: dict) -> list[StepVerdict]:
    """Every sealed record from both sides, ours first then the opponent's,
    each side in its recorded order (which is protocol order)."""
    out: list[StepVerdict] = []
    for side_key, side in (("records", "ours"), ("opponent_records", "opponent")):
        for rec in doc.get(side_key) or []:
            payload = rec.get("payload")
            nonce = rec.get("nonce")
            stored = str(rec.get("commit") or "")
            if not isinstance(payload, dict) or not isinstance(nonce, str) or not nonce:
                recomputed = "<unverifiable: missing payload or nonce>"
            else:
                recomputed = reference_commit(payload, nonce)
            out.append(
                StepVerdict(
                    index=len(out),
                    side=side,
                    step=int(payload.get("step", -1)) if isinstance(payload, dict) else -1,
                    payload=payload if isinstance(payload, dict) else {},
                    nonce=nonce if isinstance(nonce, str) else "",
                    stored_commit=stored,
                    recomputed_commit=recomputed,
                )
            )
    return out


def overall_verdict(steps: list[StepVerdict]) -> str:
    """One tampered step invalidates the whole match (book 7.5)."""
    if not steps:
        return TAMPERED
    return VERIFIED if all(s.ok for s in steps) else TAMPERED


def verify_file(path: str | Path) -> tuple[str, list[StepVerdict]]:
    steps = iter_steps(load_log(path))
    return overall_verdict(steps), steps
