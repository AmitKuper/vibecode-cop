from __future__ import annotations

import pytest

pytest.skip("module removed in restructure", allow_module_level=True)


import copy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from cop_worker.adaptive import reference_v3 as ref
from cop_worker.adaptive.introspector import IntrospectionResult, ToolSchema
from cop_worker.adaptive.mapping_plan import (
    CompatibilityVerdict,
    FieldMapping,
    PhaseMapping,
    ProtocolMappingPlan,
)
from cop_worker.adaptive.protocol_agent import ProtocolUnderstandingAgent
from cop_worker.peer_step0 import (
    Step0ExchangeError,
    accept_remote_signed_declaration,
    build_local_signed_declaration,
    persist_step0_evidence,
)
from pydantic import ValidationError

from cop_worker.domain.config_validator import GameConfig
from cop_worker.step0.declaration import (
    DeclarationAgreement,
    PeerDeclaration,
    SignedDeclaration,
)
from cop_worker.step0.signing import generate_key_pair, sign
from league_manager.reports.base import ReportContext
from league_manager.reports.gmail_report import GmailReportPlugin


def _intro(tools: list[ToolSchema] | None = None) -> IntrospectionResult:
    return IntrospectionResult(
        server_name="coverage-peer",
        server_version="3",
        protocol_version="2025-06-18",
        tools=tools or [],
        resources=[],
        prompts=[],
        raw_capabilities={"tools": {}},
        schema_digest="coverage-schema",
    )


def _reference_intro() -> IntrospectionResult:
    return _intro(
        [
            ToolSchema(
                name=name,
                description=name,
                input_schema={
                    "type": "object",
                    "properties": {argument: {"type": "object"}},
                    "required": [argument],
                },
            )
            for name, argument in ref.REFERENCE_V3_TOOLS.items()
        ]
    )


def _greetings() -> tuple[dict, dict]:
    terms = ref.default_terms()
    ours = ref.build_negotiation(
        terms=terms,
        nonce="11" * 16,
        group_id="sparring-ours",
        group_name="Ours",
        role="police",
        sub_game_number=1,
    )
    theirs = ref.build_negotiation(
        terms=terms,
        nonce="22" * 16,
        group_id="sparring-theirs",
        group_name="Theirs",
        role="thief",
        sub_game_number=1,
        opponent_group="sparring-ours",
    )
    return ours, theirs


def _turn(step: int = 1, commit: str = "a" * 64, **over) -> dict:
    return {
        "step": step,
        "sender": "police",
        "commit": commit,
        "hint": "",
        "smell_grid": {},
        **over,
    }


def _private(step: int = 1, move: str = "STAY", nonce: str = "44" * 16) -> tuple[dict, dict]:
    payload = {"step": step, "move": move, "position": [0, 0]}
    return ref.build_turn(
        record_payload=payload,
        nonce=nonce,
        sender="police",
        hint="",
        smell_grid={},
    )


def test_reference_v3_construction_rejects_every_invalid_boundary() -> None:
    for payload, nonce in (([], "x"), ({}, 7), ({}, "")):
        with pytest.raises(ref.ReferenceV3Error, match="commit requires"):
            ref.reference_commit(payload, nonce)

    with pytest.raises(ref.ReferenceV3Error, match="unknown"):
        ref.default_terms({"not_a_term": True})
    with pytest.raises(ref.ReferenceV3Error, match="six-game"):
        ref.default_terms({"num_games": 5})
    with pytest.raises(ref.ReferenceV3Error, match="surface"):
        ref.ReferenceV3Profile.from_introspection(_intro())

    for role, number in (("spy", 1), ("police", 0), ("thief", 7)):
        with pytest.raises(ref.ReferenceV3Error, match="police/thief"):
            ref.build_negotiation(
                terms=ref.default_terms(),
                nonce="11" * 16,
                group_id="ours",
                group_name="Ours",
                role=role,
                sub_game_number=number,
            )


def test_reference_v3_negotiation_refusal_matrix() -> None:
    ours, theirs = _greetings()
    assert ref.verify_negotiation(ours, theirs).opponent_group == "sparring-theirs"

    cases: list[tuple[dict | None, str]] = [(None, "SPAR-N01")]
    missing = copy.deepcopy(theirs)
    missing["terms"].pop("setting")
    cases.append((missing, "SPAR-N02"))
    extended = copy.deepcopy(theirs)
    extended["terms"]["extension"] = True
    cases.append((extended, "SPAR-N02"))
    changed = copy.deepcopy(theirs)
    changed["terms"]["setting"] = "Elsewhere"
    cases.append((changed, "SPAR-N03"))
    bad_signature = copy.deepcopy(theirs)
    bad_signature["nonce"] = 7
    cases.append((bad_signature, "SPAR-N04"))
    scent = copy.deepcopy(theirs)
    scent["scent_model_sha256"] = "0" * 64
    cases.append((scent, "SPAR-N05"))
    wire = copy.deepcopy(theirs)
    wire["wire_shape_sha256"] = "0" * 64
    cases.append((wire, "SPAR-N05"))
    sub_game = copy.deepcopy(theirs)
    sub_game["sub_game_number"] = 2
    cases.append((sub_game, "SPAR-N06"))
    collision = copy.deepcopy(theirs)
    collision["role"] = "police"
    cases.append((collision, "SPAR-N07"))
    anonymous = copy.deepcopy(theirs)
    anonymous.pop("group_id")
    anonymous["identity"].pop("group_id")
    cases.append((anonymous, "SPAR-N08"))
    uid = copy.deepcopy(theirs)
    uid["game_uid"] = "wrong"
    cases.append((uid, "SPAR-N10"))

    for payload, code in cases:
        with pytest.raises(ref.ReferenceV3Error, match=code):
            ref.verify_negotiation(ours, payload)

    silent_uid = copy.deepcopy(theirs)
    silent_uid["game_uid"] = 123
    assert ref.verify_negotiation(ours, silent_uid).game_uid


def test_reference_v3_turn_validation_and_receiver_matrix() -> None:
    invalid = [
        ({}, "missing fields"),
        (_turn(sender="observer"), "sender"),
        (_turn(step=0), "positive"),
        (_turn(commit="short"), "SHA-256"),
        (_turn(commit="g" * 64), "hexadecimal"),
        (_turn(sender="thief", barrier_placed=[0, 0]), "only police"),
        (_turn(hint=" ".join(["word"] * 16)), "word cap"),
        (_turn(smell_grid=[]), "smell_grid"),
        (_turn(smell_grid={"0,0": "high"}), "smell_grid"),
    ]
    for message, reason in invalid:
        with pytest.raises(ref.ReferenceV3Error, match=reason):
            ref.validate_turn(message)

    inbox = ref.ReferenceV3Inbox(window=2)
    second = _turn(step=2, commit="b" * 64)
    assert inbox.offer(second) == []
    assert inbox.offer(second) == []
    with pytest.raises(ref.ReferenceV3EquivocationError, match="buffered"):
        inbox.offer(_turn(step=2, commit="c" * 64))
    first = _turn()
    assert inbox.offer(first) == [first, second]
    assert inbox.offer(first) == []
    stale = ref.ReferenceV3Inbox(window=2, next_step=3)
    assert stale.offer(_turn(step=1, commit="d" * 64)) == []
    with pytest.raises(ref.ReferenceV3EquivocationError, match="already-played"):
        inbox.offer(_turn(commit="e" * 64))
    with pytest.raises(ref.ReferenceV3Error, match="reorder window"):
        ref.ReferenceV3Inbox(window=1).offer(_turn(step=3))


def test_reference_v3_audit_rejects_malformed_unbound_and_equivocal_reveals() -> None:
    assert ref.verify_audit({}, {}) == (False, ["audit payload has no records list"])

    malformed = {"sender": "thief", "records": ["bad", {}, {"payload": {}}]}
    ok, errors = ref.verify_audit(malformed, {})
    assert not ok
    assert len(errors) == 3

    _, good = _private()
    tampered = copy.deepcopy(good)
    tampered["commit"] = "0" * 64
    ok, errors = ref.verify_audit({"records": [tampered]}, {})
    assert not ok
    assert "commitment mismatch" in errors[0]

    _, other = _private(move="MOVE:E", nonce="55" * 16)
    ok, errors = ref.verify_audit({"records": [good, other]}, {})
    assert not ok
    assert "two commitments" in errors[0]

    ok, errors = ref.verify_audit({"records": [good]}, {1: good["commit"], 2: "f" * 64})
    assert not ok
    assert "played step 2" in errors[0]


@pytest.mark.asyncio
async def test_reference_v3_session_persistence_and_local_equivocation() -> None:
    calls: list[tuple[str, dict]] = []

    async def caller(name: str, params: dict) -> dict:
        calls.append((name, params))
        return {"ok": True}

    session = ref.ReferenceV3Session(caller)
    turn, record = _private()
    wrong = {**record, "commit": "0" * 64}
    with pytest.raises(ref.ReferenceV3Error, match="different commits"):
        await session.send_turn(turn, wrong)

    await session.send_turn(turn, record)
    await session.send_turn(turn, record)
    changed_turn, changed_record = _private(move="MOVE:E", nonce="55" * 16)
    with pytest.raises(ref.ReferenceV3EquivocationError, match="local commit"):
        await session.send_turn(changed_turn, changed_record)
    with pytest.raises(ref.ReferenceV3Error, match="result claim"):
        await session.send_audit("police", "draw")

    await session.send_audit("police", "timeout")
    session.receive_negotiation({"terms": {}})
    session.receive_audit({"records": []})
    session.receive_control({"kind": "status"})
    assert len(session.local_records) == 1
    assert [name for name, _ in calls] == ["receive_turn", "receive_turn", "submit_audit"]


def test_reference_v3_core_assertion_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ref, "reference_commit", lambda *_args: "not-the-vector")
    with pytest.raises(ref.ReferenceV3Error, match="CORE"):
        ref.assert_core_vectors()


def test_protocol_agent_maps_every_canonical_phase_branch() -> None:
    agent = ProtocolUnderstandingAgent()
    fields = {
        "game_id",
        "step",
        "role",
        "phase",
        "config_sha256",
        "timestamp",
        "signature",
        "gamelet",
        "commitment",
        "hint",
        "move",
        "nonces",
        "signed_audit_summary",
        "reason",
        "result_hash",
        "signed_agreement",
    }
    props = {name: {"type": "string"} for name in fields}
    phases = (
        "start_game",
        "commit",
        "reveal",
        "final_audit",
        "audit_summary",
        "game_end",
        "result_agreement",
        "abort",
        "unknown",
    )
    for phase in phases:
        mapped = agent._map_canonical_fields(phase, props)
        assert mapped
        assert all(item.remote_field in props for item in mapped)
    assert agent._map_canonical_fields("unknown", {}) == []

    signed = _intro(
        [
            ToolSchema(
                name="action",
                description="action",
                input_schema={
                    "type": "object",
                    "properties": {
                        "game_id": {},
                        "message_json": {},
                        "signature": {},
                    },
                },
            ),
            ToolSchema(
                name="start_game",
                description="start",
                input_schema={
                    "type": "object",
                    "properties": {"message_json": {}, "signature": {}},
                },
            ),
            ToolSchema(
                name="conformance_check",
                description="conformance",
                input_schema={"type": "object", "properties": {}},
            ),
        ]
    )
    assert agent._heuristic_plan(signed).is_compatible()


def test_protocol_agent_rejects_llm_selected_unknown_tools_and_fields() -> None:
    agent = ProtocolUnderstandingAgent()
    intro = _intro(
        [
            ToolSchema(
                name="known",
                description="known",
                input_schema={"type": "object", "properties": {"field": {}}},
            )
        ]
    )
    unknown_tool = ProtocolMappingPlan(
        remote_tool_name="missing",
        remote_server_name="coverage-peer",
        remote_schema_digest="coverage-schema",
        conformance_tool="missing",
        verdict=CompatibilityVerdict.COMPATIBLE,
    )
    with pytest.raises(ValueError, match="conformance tool"):
        agent._validate_remote_plan(unknown_tool, intro)

    bad_field = ProtocolMappingPlan(
        remote_tool_name="known",
        remote_server_name="coverage-peer",
        remote_schema_digest="coverage-schema",
        conformance_tool="known",
        phase_mappings=[
            PhaseMapping(
                phase="commit",
                remote_tool="known",
                field_mappings=[FieldMapping("game_id", "missing")],
            )
        ],
        verdict=CompatibilityVerdict.COMPATIBLE,
    )
    with pytest.raises(ValueError, match="unknown field"):
        agent._validate_remote_plan(bad_field, intro)


def test_appendix_f_validator_reports_all_fixed_and_bounded_failures() -> None:
    with pytest.raises(ValidationError, match="Appendix-F") as caught:
        GameConfig(
            grid_size=6,
            max_barriers=13,
            max_moves=34,
            survival_threshold=36,
            scoring={
                "capture_cop": 19,
                "capture_thief": 4,
                "survival_cop": 4,
                "survival_thief": 9,
            },
        )
    text = str(caught.value)
    for field in (
        "grid_size",
        "max_barriers",
        "max_moves",
        "survival_threshold",
        "capture_cop",
    ):
        assert field in text


def test_step0_evidence_requires_complete_input_and_persists_both_profile_paths(tmp_path) -> None:
    runtime = SimpleNamespace(
        _local_step0={},
        _remote_step0={},
        _step0_agreements={},
        _adaptive_profile=None,
        _inbound_profile_hash="inbound",
        games_dir=tmp_path,
    )
    with pytest.raises(Step0ExchangeError, match="incomplete"):
        persist_step0_evidence(runtime, "g01")

    local = MagicMock()
    local.to_dict.return_value = {"side": "local"}
    remote = MagicMock()
    remote.to_dict.return_value = {"side": "remote"}
    agreement = DeclarationAgreement.from_declarations("g01", "a" * 64, "b" * 64)
    runtime._local_step0["g01"] = local
    runtime._remote_step0["g01"] = remote
    runtime._step0_agreements["g01"] = agreement
    persist_step0_evidence(runtime, "g01")
    assert (tmp_path / "g01" / "step0_evidence.json").is_file()

    runtime._adaptive_profile = SimpleNamespace(to_dict=lambda: {"profile": "locked"})
    persist_step0_evidence(runtime, "g01")


def _signed_step0(**over) -> SignedDeclaration:
    private_key, public_key = generate_key_pair()
    fields = {
        "game_uid": "g01",
        "config_sha256": "c" * 64,
        "canonical_config_sha256": "c" * 64,
        "protocol_version": "1.0",
        "counted_mode": True,
        "adapter_mapping_hash": "p" * 64,
        "public_key_hex": public_key.hex(),
    }
    fields.update(over)
    declaration = PeerDeclaration(**fields)
    signature = sign(private_key, declaration.canonical_bytes()).hex()
    return SignedDeclaration(declaration, signature)


def _step0_runtime(local: SignedDeclaration, *, counted: bool = True):
    return SimpleNamespace(
        config_sha256="c" * 64,
        counted_mode=counted,
        orchestrator=SimpleNamespace(validate_counted_declaration=lambda _decl: []),
        _remote_step0={},
        _local_step0={"g01": local},
        _step0_agreements={},
    )


def test_step0_signed_refusal_matrix_and_lazy_local_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = _signed_step0()
    runtime = _step0_runtime(local)

    with pytest.raises(Step0ExchangeError, match="omitted"):
        accept_remote_signed_declaration(runtime, "g01", None)
    with pytest.raises(Step0ExchangeError, match="malformed"):
        accept_remote_signed_declaration(runtime, "g01", {"declaration": {}})

    cases = [
        (_signed_step0(game_uid="other"), "game_uid mismatch"),
        (_signed_step0(config_sha256="d" * 64), "config hash mismatch"),
        (_signed_step0(protocol_version="2.0"), "protocol version"),
        (_signed_step0(counted_mode=False), "not COUNTED"),
        (_signed_step0(adapter_mapping_hash=""), "ProtocolProfile hash"),
    ]
    for signed, reason in cases:
        with pytest.raises(Step0ExchangeError, match=reason):
            accept_remote_signed_declaration(runtime, "g01", signed.to_dict())

    rejected = _step0_runtime(local)
    rejected.orchestrator.validate_counted_declaration = lambda _decl: ["bad identity"]
    with pytest.raises(Step0ExchangeError, match="counted declaration rejected"):
        accept_remote_signed_declaration(rejected, "g01", _signed_step0().to_dict())

    uncounted = _step0_runtime(local, counted=False)
    agreement = accept_remote_signed_declaration(uncounted, "g01", _signed_step0().to_dict())
    assert agreement.game_uid == "g01"

    lazy = _step0_runtime(local, counted=False)
    lazy._local_step0.clear()
    monkeypatch.setattr(
        "agent.peer_step0.build_local_signed_declaration",
        lambda _runtime, _game_id: local,
    )
    assert accept_remote_signed_declaration(lazy, "g01", _signed_step0().to_dict()).game_uid

    with pytest.raises(Step0ExchangeError, match="unavailable"):
        build_local_signed_declaration(SimpleNamespace(orchestrator=None), "g01")


def _report_context(tmp_path) -> ReportContext:
    return ReportContext(
        game_id="g01",
        role="cop",
        group_id="group",
        opponent_group_id="peer",
        game_dir=tmp_path,
        game_state={},
        result={"winner": "cop"},
        start_timestamp="2026-08-06T00:00:00Z",
        end_timestamp="2026-08-06T00:01:00Z",
        config_hash="c" * 64,
        log_hash="d" * 64,
        required_files={},
        optional_files={},
    )


@pytest.mark.asyncio
async def test_gmail_plugin_draft_unknown_and_existing_invalid_token_paths(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _report_context(tmp_path)
    draft = GmailReportPlugin(
        mode="draft",
        attach_required_files=False,
        attach_markdown_summary=False,
    )
    result = await draft.generate(context)
    assert result.ok and result.status == "draft"

    unknown = GmailReportPlugin(
        mode="not-a-mode",
        attach_required_files=False,
        attach_markdown_summary=False,
    )
    result = await unknown.generate(context)
    assert not result.ok and result.error_code == "invalid_mode"

    token = tmp_path / "token.json"
    token.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "agent.reports.gmail_report.load_oauth_credentials",
        lambda _path: (_ for _ in ()).throw(RuntimeError("invalid OAuth token")),
    )
    send = GmailReportPlugin(
        mode="send",
        token_path=token,
        attach_required_files=False,
        attach_markdown_summary=False,
    )
    result = await send.generate(context)
    assert not result.ok and result.error_code == "gmail_auth_missing"
