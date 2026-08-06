"""Deterministic compatibility layer for the league kit's ``reference-v3`` wire.

This dialect is intentionally separate from the course-native eight-call protocol.  A
``reference-v3`` half-turn sends one sealed record and defers the move and nonce reveal to the
bilateral audit.  Treating it as a collection of renamed ``commit``/``reveal`` tools would leak
the nonce or send two messages where the peer expects one.

The protocol-understanding agent may select this module only before a game starts.  Gameplay is
then handled by :class:`ReferenceV3Session`; it performs no LLM calls and accepts no secrets or
signing authority from discovery data.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any

from agent.adaptive.introspector import IntrospectionResult

REFERENCE_V3_DIALECT = "copthief-league-reference-v3"
REFERENCE_V3_TOOLS = {
    "negotiate": "message",
    "receive_turn": "message",
    "submit_audit": "payload",
    "receive_control": "message",
}
REFERENCE_V3_WIRE_LOCK = "229ae6487a418c3fcb6da9be404de2f2533c288ebc228811bff6dedc4164d6f7"
REFERENCE_V3_SCENT_LOCK = "81ebee59640e80eae8ca9ee5f86abd26e7edf5cdbb27d15925cb6ee45ca6ddf4"

TERMS_KEYS = (
    "board_size",
    "smell_grid_size",
    "decay_per_step",
    "emit_intensity",
    "min_center_intensity",
    "max_steps",
    "barriers_max",
    "setting",
    "hint_max_words",
    "axis_origin_corner",
    "axis_start_index",
    "thief_start",
    "cop_start",
    "num_games",
)


class ReferenceV3Error(ValueError):
    """A deterministic refusal of an incompatible or invalid reference-v3 message."""


class ReferenceV3EquivocationError(ReferenceV3Error):
    """A played step was resent under a different commitment."""


def canonical_json(value: object) -> str:
    """The kit's CORE canonical form: compact, sorted, native UTF-8 text."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def reference_commit(payload: dict, nonce: str) -> str:
    """SHA256(canonical_json(payload) + ``|`` + nonce), exactly as the kit vectors pin."""
    if not isinstance(payload, dict) or not isinstance(nonce, str) or not nonce:
        raise ReferenceV3Error("a reference-v3 commit requires a dict payload and non-empty nonce")
    return hashlib.sha256(f"{canonical_json(payload)}|{nonce}".encode()).hexdigest()


def terms_signature(terms: dict, nonce: str) -> str:
    return reference_commit(terms, nonce)


def derive_game_id(group_a: str, group_b: str) -> str:
    return "-vs-".join(sorted((group_a, group_b)))


def derive_game_uid(terms: dict, group_a: str, group_b: str) -> str:
    pair = "|".join(sorted((group_a, group_b)))
    digest = hashlib.sha256(f"{canonical_json(terms)}|{pair}".encode()).digest()
    return str(uuid.UUID(bytes=digest[:16]))


def default_terms(config: dict | None = None) -> dict:
    """Return the closed fourteen-field agreement, allowing explicit pairwise overrides."""
    config = dict(config or {})
    terms = {
        "board_size": 7,
        "smell_grid_size": 5,
        "decay_per_step": 0.1,
        "emit_intensity": 0.9,
        "min_center_intensity": 0.5,
        "max_steps": 35,
        "barriers_max": 14,
        "setting": "Haifa",
        "hint_max_words": 15,
        "axis_origin_corner": "top-left",
        "axis_start_index": 0,
        "thief_start": [3, 3],
        "cop_start": [0, 0],
        "num_games": 6,
    }
    unknown = set(config) - set(TERMS_KEYS)
    if unknown:
        raise ReferenceV3Error(f"unknown reference-v3 agreement terms: {sorted(unknown)}")
    terms.update(config)
    if set(terms) != set(TERMS_KEYS) or terms["num_games"] != 6:
        raise ReferenceV3Error("reference-v3 terms must be the closed 14-key, six-game agreement")
    return terms


def _object_argument(tool, argument: str) -> bool:
    schema = tool.input_schema if isinstance(tool.input_schema, dict) else {}
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    prop = properties.get(argument)
    return (
        isinstance(properties, dict)
        and set(properties) == {argument}
        and argument in required
        and isinstance(prop, dict)
        and prop.get("type") == "object"
    )


def is_reference_v3_surface(introspection: IntrospectionResult) -> bool:
    """Recognize the exact four-tool reference surface from sanitized MCP schemas.

    Extra advertised tools are tolerated, but the four protected names must each have the exact
    one-object argument (including the ``submit_audit(payload)`` asymmetry).  Semantic agreement
    is established later by the signed negotiation and model lock, never from descriptions.
    """
    for tool_name, argument in REFERENCE_V3_TOOLS.items():
        tool = introspection.get_tool(tool_name)
        if tool is None or not _object_argument(tool, argument):
            return False
    return True


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
) -> dict:
    if role not in {"police", "thief"} or sub_game_number not in range(1, 7):
        raise ReferenceV3Error("reference-v3 requires police/thief and sub-game 1..6")
    wire = {
        "terms": terms,
        "nonce": nonce,
        "signature": terms_signature(terms, nonce),
        "group_id": group_id,
        "role": role,
        "sub_game_number": sub_game_number,
        "identity": {
            "group_id": group_id,
            "group_name": group_name,
            "llm_model": "role-specific-recurrent-policy",
            "mcp_servers": {},
            "repos": {},
            "members": [],
        },
        "scent_model_sha256": REFERENCE_V3_SCENT_LOCK,
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
    timestamp: str = "",
    barrier_placed: list[int] | None = None,
    capture_claim: list[int] | None = None,
    claim_response: dict | None = None,
    win_claim: dict | None = None,
) -> tuple[dict, dict]:
    """Return (wire turn, private audit record); the nonce never enters the wire turn."""
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


class ReferenceV3Session:
    """Non-blocking four-tool session used by a game loop after profile lock."""

    def __init__(self, tool_caller, *, reorder_window: int = 4) -> None:
        self._call = tool_caller
        self.turns = ReferenceV3Inbox(window=reorder_window)
        self.agreements: deque[dict] = deque()
        self.audits: deque[dict] = deque()
        self.controls: deque[dict] = deque()
        self.local_records: list[dict] = []
        self._local_records_by_step: dict[int, dict] = {}
        self.per_turn_llm_calls = 0

    async def send_negotiation(self, message: dict) -> dict:
        return await self._call("negotiate", {"message": message})

    async def send_turn(self, turn: dict, private_record: dict) -> dict:
        validate_turn(turn)
        if turn["commit"] != private_record.get("commit"):
            raise ReferenceV3Error("wire turn and private audit record have different commits")
        # Durable callers persist before invoking this method.  Keep one local record before the
        # network call so an acknowledgement loss retries the same bytes idempotently.
        step = int(turn["step"])
        prior = self._local_records_by_step.get(step)
        if prior is not None and prior.get("commit") != turn["commit"]:
            raise ReferenceV3EquivocationError(f"different local commit retry for step {step}")
        if prior is None:
            stored = dict(private_record)
            self._local_records_by_step[step] = stored
            self.local_records.append(stored)
        return await self._call("receive_turn", {"message": turn})

    async def send_audit(self, sender: str, result_claim: str) -> dict:
        if result_claim not in {"capture", "survival", "timeout", "technical_loss"}:
            raise ReferenceV3Error("invalid reference-v3 result claim")
        payload = {"sender": sender, "records": self.local_records, "result_claim": result_claim}
        return await self._call("submit_audit", {"payload": payload})

    async def send_control(self, message: dict) -> dict:
        return await self._call("receive_control", {"message": message})

    def receive_turn(self, message: dict) -> list[dict]:
        return self.turns.offer(message)

    def receive_negotiation(self, message: dict) -> None:
        self.agreements.append(dict(message))

    def receive_audit(self, payload: dict) -> None:
        self.audits.append(dict(payload))

    def receive_control(self, message: dict) -> None:
        self.controls.append(dict(message))


def register_reference_v3_tools(mcp, session: ReferenceV3Session) -> None:
    """Expose the exact non-blocking FastMCP surface used by the unmodified league kit."""

    @mcp.tool
    def negotiate(message: dict) -> dict:
        """Receive the opponent's signed game agreement."""
        session.receive_negotiation(message)
        return {"ok": True}

    @mcp.tool
    def receive_turn(message: dict) -> dict:
        """Receive the opponent's turn message."""
        session.receive_turn(message)
        return {"ok": True}

    @mcp.tool
    def submit_audit(payload: dict) -> dict:
        """Receive the opponent's end-of-game audit reveal (records + nonces)."""
        session.receive_audit(payload)
        return {"ok": True}

    @mcp.tool
    def receive_control(message: dict) -> dict:
        """Receive an opponent control signal (enable / status / restart / quit)."""
        session.receive_control(message)
        return {"ok": True}


def assert_core_vectors() -> None:
    """Fail closed if this interpreter cannot reproduce the kit's published CORE vectors."""
    cases: list[tuple[dict[str, Any], str, str]] = [
        (
            {
                "step": 0,
                "type": "system_spec",
                "spec": {"os": "Linux", "cpu_cores": 4, "ram_gb": 16.0, "vram_gb": 0.0},
                "model": "cli-default",
                "code_version": "1.0",
                "group_name": "Example-Team",
                "sub_game_number": 1,
            },
            "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
            "69c9a786d18829990291cd0ffb768eacfa009011b0c89a6f4f32330551e2003e",
        ),
        (
            {
                "step": 2,
                "state": "grid=7x7;self=[2, 4];barriers=[[1, 1]]",
                "position": [2, 4],
                "move": "MOVE:N",
                "intent": "lie",
                "hint": "אני ליד הכיכר 🙂",
            },
            "deadbeefcafef00dfeedface00c0ffee",
            "2caaeb0a7e656868b85166a9ebe34226bae4fdcb79cb7a0a23759121769d9338",
        ),
    ]
    for payload, nonce, expected in cases:
        if reference_commit(payload, nonce) != expected:
            raise ReferenceV3Error("reference-v3 CORE commit vector mismatch")
