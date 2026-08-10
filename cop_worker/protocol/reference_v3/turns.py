"""Sealed half-turns: inbox dedup, validation, construction, and audit verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from cop_worker.protocol.reference_v3.constants import (
    ReferenceV3EquivocationError,
    ReferenceV3Error,
)
from cop_worker.protocol.reference_v3.hashing import reference_commit


@dataclass
class ReferenceV3Inbox:
    """At-least-once ordered receiver: commit-keyed dedupe and bounded reorder."""

    window: int = 4
    next_step: int = 1
    played: dict[int, str] = field(default_factory=dict)
    buffered: dict[int, dict] = field(default_factory=dict)

    def offer(self, message: dict) -> list[dict]:
        validate_turn(message)
        step, commit = int(message["step"]), message["commit"]
        if step in self.played:
            if self.played[step] != commit:
                raise ReferenceV3EquivocationError(
                    f"different commit for already-played step {step}"
                )
            return []
        if step < self.next_step:
            return []
        if step - self.next_step > self.window:
            raise ReferenceV3Error(f"step {step} is past reorder window {self.window}")
        if step != self.next_step:
            prior = self.buffered.get(step)
            if prior is not None and prior.get("commit") != commit:
                raise ReferenceV3EquivocationError(f"different buffered commit for step {step}")
            self.buffered[step] = dict(message)
            return []
        ready = [dict(message)]
        self.played[step] = commit
        self.next_step += 1
        while self.next_step in self.buffered:
            item = self.buffered.pop(self.next_step)
            self.played[self.next_step] = item["commit"]
            ready.append(item)
            self.next_step += 1
        return ready


def validate_turn(message: dict) -> None:
    required = {"step", "sender", "commit", "hint", "smell_grid"}
    if not isinstance(message, dict) or not required.issubset(message):
        raise ReferenceV3Error(f"turn missing fields: {sorted(required - set(message or {}))}")
    if message["sender"] not in {"police", "thief"}:
        raise ReferenceV3Error("turn sender must be police or thief")
    if not isinstance(message["step"], int) or message["step"] < 1:
        raise ReferenceV3Error("turn step must be a positive integer")
    commit = message["commit"]
    if not isinstance(commit, str) or len(commit) != 64:
        raise ReferenceV3Error("turn commit must be a SHA-256 hex digest")
    try:
        int(commit, 16)
    except ValueError as exc:
        raise ReferenceV3Error("turn commit must be hexadecimal") from exc
    if message.get("barrier_placed") is not None and message["sender"] != "police":
        raise ReferenceV3Error("only police may declare a barrier")
    if len(str(message["hint"]).split()) > 15:
        raise ReferenceV3Error("turn hint exceeds the negotiated default word cap")
    grid = message["smell_grid"]
    if not isinstance(grid, dict) or any(not isinstance(v, (int, float)) for v in grid.values()):
        raise ReferenceV3Error("smell_grid must map string cells to numeric intensities")


def build_turn(
    *,
    record_payload: dict,
    nonce: str,
    sender: str,
    hint: str,
    smell_grid: dict[str, float],
    timestamp: str | None = None,
    barrier_placed: list[int] | None = None,
    capture_claim: list[int] | None = None,
    claim_response: dict | None = None,
    win_claim: dict | None = None,
) -> tuple[dict, dict]:
    """Return (wire turn, private audit record); the nonce never enters the wire turn.

    ``timestamp`` defaults to *now* in ISO-8601 UTC rather than to ``""``: at least one live
    peer (imreeyal) refuses a turn carrying an empty stamp at validation, before any state
    change, which would turn every turn we send into a refusal and every sub-game into a
    technical loss. The stamp is deliberately NOT part of ``record_payload``, so it never
    enters the commit preimage and cannot affect an audit.
    """
    if not timestamp:
        timestamp = datetime.now(UTC).isoformat()
    record = {
        "payload": dict(record_payload),
        "nonce": nonce,
        "commit": reference_commit(record_payload, nonce),
    }
    turn = {
        "step": int(record_payload["step"]),
        "sender": sender,
        "commit": record["commit"],
        "hint": hint,
        "smell_grid": dict(smell_grid),
        "timestamp": timestamp,
        "barrier_placed": barrier_placed,
        "capture_claim": capture_claim,
        "claim_response": claim_response,
        "win_claim": win_claim,
    }
    validate_turn(turn)
    return turn, record


def verify_audit(payload: dict, played: dict[int, str]) -> tuple[bool, list[str]]:
    """Rehash all records and bind every received commitment to its audit reveal."""
    errors: list[str] = []
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        return False, ["audit payload has no records list"]
    revealed: dict[int, str] = {}
    for index, record in enumerate(payload["records"]):
        if not isinstance(record, dict):
            errors.append(f"record {index} is not an object")
            continue
        body, nonce, claimed = record.get("payload"), record.get("nonce"), record.get("commit")
        if not isinstance(body, dict) or not isinstance(nonce, str) or not isinstance(claimed, str):
            errors.append(f"record {index} lacks payload/nonce/commit")
            continue
        if reference_commit(body, nonce) != claimed:
            errors.append(f"step {body.get('step', -1)} commitment mismatch")
            continue
        step = body.get("step")
        if isinstance(step, int) and step >= 1:
            if step in revealed and revealed[step] != claimed:
                errors.append(f"step {step} appears under two commitments")
            revealed[step] = claimed
    for step, commit in sorted(played.items()):
        if revealed.get(step) != commit:
            errors.append(f"played step {step} is missing or revealed under another commit")
    return not errors, errors
