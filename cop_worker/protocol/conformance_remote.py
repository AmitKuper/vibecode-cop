"""Remote conformance probing against a live peer (mixin)."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable

from cop_worker.protocol.conformance_types import (
    _PLACEHOLDER_GAME_ID,
    ConformanceReport,
    ProbeOutcome,
    _signed_placeholder_envelope,
)
from cop_worker.protocol.mapping_plan import ProtocolMappingPlan

logger = logging.getLogger(__name__)


class ConformanceRemoteMixin:
    """Live-peer probe execution."""

    async def run_remote(
        self,
        tool_caller: Callable[[str, dict], Awaitable[dict]],
    ) -> ConformanceReport:
        """Exercise mapped tools with inert, deliberately invalid envelopes.

        A conforming course peer must reject these probes before mutating game
        state because the game id, configuration hash, and signature are
        placeholders. Repeating each call also checks stable/idempotent failure
        behavior without revealing a real nonce, move, key, or commitment.
        """
        outcomes: list[ProbeOutcome] = []
        for phase in sorted(ProtocolMappingPlan.REQUIRED_PHASES):
            try:
                canonical = self._remote_placeholder(phase)
                request = self._adapter.adapt_request(phase, canonical)
                first = await tool_caller(request.tool_name, request.params)
                second = await tool_caller(request.tool_name, request.params)
                if not isinstance(first, dict) or not isinstance(second, dict):
                    raise TypeError("remote probe response must be an object")
                if first.get("ok") is True or second.get("ok") is True:
                    raise ValueError("peer accepted an invalid conformance envelope")
                first_shape = self._stable_response_shape(first)
                second_shape = self._stable_response_shape(second)
                if first_shape != second_shape:
                    raise ValueError("non-idempotent response to identical inert probe")
                self._adapter.adapt_response(phase, first)
                outcomes.append(
                    ProbeOutcome(
                        f"remote_{phase}",
                        True,
                        notes="mapped tool reached and invalid envelope rejected stably",
                    )
                )
            except Exception as exc:
                outcomes.append(ProbeOutcome(f"remote_{phase}", False, error=str(exc)))
                continue
            try:
                canonical = self._remote_placeholder(phase)
                mapped = self._adapter.adapt_request(phase, canonical)
                full_digest = hashlib.sha256(
                    json.dumps(
                        mapped.params, sort_keys=True, separators=(",", ":"), default=str
                    ).encode("utf-8")
                ).hexdigest()
                key = hashlib.sha256(f"{_PLACEHOLDER_GAME_ID}:{phase}".encode()).hexdigest()
                params = {
                    "phase": phase,
                    "game_id": _PLACEHOLDER_GAME_ID,
                    "request_digest": full_digest,
                    "idempotency_key": key,
                }
                first = await tool_caller(self._plan.conformance_tool, params)
                second = await tool_caller(self._plan.conformance_tool, params)
                if first != second:
                    raise ValueError("valid conformance retry was not byte-stable")
                if not isinstance(first, dict) or first.get("ok") is not True:
                    raise ValueError("remote did not accept the side-effect-free valid probe")
                if first.get("game_id") != _PLACEHOLDER_GAME_ID or first.get("phase") != phase:
                    raise ValueError("valid conformance probe corrupted protected fields")
                if first.get("idempotent") is not True or first.get("side_effects") != 0:
                    raise ValueError(
                        "valid conformance probe lacks idempotent no-side-effect proof"
                    )
                semantic_proofs = (
                    "canonical_order",
                    "canonical_json_bytes",
                    "commitment_binding",
                    "nonce_final_audit_only",
                    "comprehensive_audit",
                    "result_agreement",
                )
                missing_proofs = [name for name in semantic_proofs if first.get(name) is not True]
                if missing_proofs:
                    raise ValueError(
                        f"valid conformance probe lacks semantic proofs: {missing_proofs}"
                    )
                outcomes.append(
                    ProbeOutcome(
                        f"remote_valid_{phase}",
                        True,
                        notes="valid semantic probe accepted twice without state mutation",
                    )
                )
            except Exception as exc:
                outcomes.append(ProbeOutcome(f"remote_valid_{phase}", False, error=str(exc)))
        return ConformanceReport(all(p.passed for p in outcomes), outcomes)

    @staticmethod
    def _stable_response_shape(response: dict) -> tuple:
        return tuple(
            (key, type(value).__name__, str(value))
            for key, value in sorted(response.items())
            if key not in {"timestamp", "request_id", "trace_id"}
        )

    @staticmethod
    def _remote_placeholder(phase: str) -> dict:
        payload = {
            "game_id": _PLACEHOLDER_GAME_ID,
            "gamelet": 1,
            "step": 1,
            "role": "cop",
            "phase": phase,
            "config_sha256": "0" * 64,
            "timestamp": "2026-01-01T00:00:00Z",
            "commitment": "0" * 64,
            "move": "STAY",
            "hint": "Protocol conformance probe.",
            "intent": "TRUTH",
            "nonces": {"1": "PROBE_NONCE_NOT_REAL"},
            "reason": "probe",
            "result_hash": "0" * 64,
            "signed_agreement": {"probe": True},
            "signed_audit_summary": {"probe": True},
        }
        return _signed_placeholder_envelope(payload)
