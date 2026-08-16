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
from dataclasses import dataclass, replace
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


def record_role(step: StepVerdict, our_role: str) -> str:
    """A record's role: the sealed ``role`` key when present, else by side.

    Some peers (nis-yar1) seal no role - then ours = our_role and the
    opponent plays the other one.
    """
    named = step.payload.get("role")
    if named in ("police", "thief"):
        return str(named)
    other = "thief" if our_role == "police" else "police"
    return our_role if step.side == "ours" else other


def chronological(steps: list[StepVerdict], our_role: str = "police") -> list[StepVerdict]:
    """Merge both sides into ONE game timeline: step-0 seals first, then each
    protocol step with the thief's record before the cop's (thief moves first).

    Without this merge a viewer walks ~35 of our steps and then ~35 opponent
    steps AGAIN from step 1 - it looks like two games in one replay, with the
    board resetting mid-timeline.
    """
    merged = sorted(
        steps,
        key=lambda s: (
            max(s.step, 0),
            0 if record_role(s, our_role) == "thief" else 1,
            s.side,  # deterministic tie-break for duplicate seals
        ),
    )
    return [replace(s, index=i) for i, s in enumerate(merged)]


def overall_verdict(steps: list[StepVerdict]) -> str:
    """One tampered step invalidates the whole match (book 7.5)."""
    if not steps:
        return TAMPERED
    return VERIFIED if all(s.ok for s in steps) else TAMPERED


def verify_file(path: str | Path) -> tuple[str, list[StepVerdict]]:
    """Verdict + the CHRONOLOGICAL timeline (verification covers every record
    regardless of order, so merging loses nothing)."""
    doc = load_log(path)
    our_role = (doc.get("summary") or {}).get("role", "police")
    steps = chronological(iter_steps(doc), our_role)
    return overall_verdict(steps), steps
