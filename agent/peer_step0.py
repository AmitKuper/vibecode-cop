"""Signed bilateral Step-0 exchange bound to the process signing identity."""

from __future__ import annotations

import json
import time
from dataclasses import asdict

from agent.step0.declaration import DeclarationAgreement, SignedDeclaration
from agent.step0.signing import sign, verify


class Step0ExchangeError(RuntimeError):
    """The peer's declaration is missing, invalid, or incompatible."""


def persist_step0_evidence(runtime, game_id: str) -> None:
    """Persist the signed bilateral declaration and locked profile without secrets."""
    local = runtime._local_step0.get(game_id)
    remote = runtime._remote_step0.get(game_id)
    agreement = runtime._step0_agreements.get(game_id)
    if local is None or remote is None or agreement is None:
        raise Step0ExchangeError("cannot persist incomplete bilateral Step-0 evidence")
    evidence = {
        "local_signed_declaration": local.to_dict(),
        "remote_signed_declaration": remote.to_dict(),
        "declaration_agreement": asdict(agreement),
        "adaptive_protocol_profile": (
            runtime._adaptive_profile.to_dict() if runtime._adaptive_profile is not None else None
        ),
        "inbound_profile_hash": runtime._inbound_profile_hash,
    }
    path = runtime.games_dir / game_id / "step0_evidence.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")


def build_local_signed_declaration(runtime, game_id: str) -> SignedDeclaration:
    """Build and sign the local declaration with the runtime-lifetime key."""
    if runtime.orchestrator is None:
        raise Step0ExchangeError("AgentOrchestrator is unavailable for Step-0")
    gamelet = runtime._gamelet_number(game_id)
    decl = runtime.orchestrator.build_step0_declaration(game_id, gamelet)
    decl.team_name = runtime.group_name
    decl.group_id = str(runtime.orchestrator_config.get("group_id", ""))
    decl.config_sha256 = runtime.config_sha256
    decl.canonical_config_sha256 = runtime.orchestrator_config.get(
        "canonical_config_sha256", runtime.config_sha256
    )
    decl.local_endpoint = runtime.my_endpoint
    decl.opponent_endpoint = getattr(runtime.opponent_client, "peer_url", "")
    decl.opponent_identity = runtime.opponent_role
    decl.timestamp_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    decl.signing_key_id = runtime._signing_key_id
    decl.public_key_hex = runtime._signing_public_key.hex()
    if runtime._adaptive_profile is not None:
        decl.adapter_mapping_hash = runtime._adaptive_profile.profile_hash
        decl.transport = runtime._adaptive_profile.remote_transport
    else:
        # Passive peers answer inside the already-introspected inbound tool call;
        # lock that deterministic response contract even though they do not make
        # an outbound gameplay call of their own.
        decl.adapter_mapping_hash = runtime._inbound_profile_hash
        decl.transport = "SSE"
    signature = sign(runtime._signing_private_key, decl.canonical_bytes()).hex()
    signed = SignedDeclaration(declaration=decl, signature_hex=signature)
    runtime._local_step0[game_id] = signed
    return signed


def accept_remote_signed_declaration(
    runtime,
    game_id: str,
    payload: dict | None,
) -> DeclarationAgreement:
    """Verify a peer declaration and lock its signing identity for this gamelet."""
    if not payload:
        raise Step0ExchangeError("peer omitted signed Step-0 declaration")
    try:
        signed = SignedDeclaration.from_dict(payload)
        public_key = bytes.fromhex(signed.declaration.public_key_hex)
        signature = bytes.fromhex(signed.signature_hex)
    except (KeyError, TypeError, ValueError) as exc:
        raise Step0ExchangeError(f"malformed peer Step-0 declaration: {exc}") from exc
    if len(public_key) != 32 or not verify(
        public_key, signed.declaration.canonical_bytes(), signature
    ):
        raise Step0ExchangeError("peer Step-0 Ed25519 signature is invalid")
    decl = signed.declaration
    if decl.game_uid != game_id:
        raise Step0ExchangeError(f"peer Step-0 game_uid mismatch: {decl.game_uid!r} != {game_id!r}")
    if decl.config_sha256 != runtime.config_sha256:
        raise Step0ExchangeError("peer Step-0 config hash mismatch")
    if decl.protocol_version != "1.0":
        raise Step0ExchangeError("peer Step-0 protocol version is incompatible")
    if runtime.counted_mode:
        if not decl.counted_mode:
            raise Step0ExchangeError("peer declaration is not COUNTED")
        errors = runtime.orchestrator.validate_counted_declaration(decl)
        if errors:
            raise Step0ExchangeError(f"peer counted declaration rejected: {errors}")
        if not decl.adapter_mapping_hash:
            raise Step0ExchangeError("peer counted declaration omitted ProtocolProfile hash")
    runtime._remote_step0[game_id] = signed
    local = runtime._local_step0.get(game_id)
    if local is None:
        local = build_local_signed_declaration(runtime, game_id)
    agreement = DeclarationAgreement.from_declarations(
        game_id,
        local.declaration.declaration_hash(),
        decl.declaration_hash(),
    )
    runtime._step0_agreements[game_id] = agreement
    return agreement
