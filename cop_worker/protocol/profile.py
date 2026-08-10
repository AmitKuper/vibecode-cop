"""ProtocolProfile: signed, hashed, cacheable record of the agreed mapping.

Both peers sign/hash the profile in Step-0. Cached by remote schema digest;
invalidated when digest changes.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field

from cop_worker.protocol.mapping_plan import ProtocolMappingPlan
from cop_worker.protocol.profile_serde import ProfileSerdeMixin
from cop_worker.protocol.transport_probe import ProbeResult


@dataclass
class ProtocolProfile(ProfileSerdeMixin):
    """Signed profile of the agreed protocol mapping between two peers.

    Included in Step-0 declaration. Cached and invalidated by schema digest.
    """

    remote_endpoint: str
    remote_transport: str
    remote_schema_digest: str
    mapping_plan: ProtocolMappingPlan
    probe_latency_ms: float
    plan_hash: str
    profile_hash: str
    timestamp_utc: str
    remote_stdio_command: tuple[str, ...] = ()
    agent_model: str = "heuristic"
    agent_version: str = "1.0"
    probe_notes: str = ""
    compatible_fixtures_passed: list[str] = field(default_factory=list)
    incompatible_fixtures_rejected: list[str] = field(default_factory=list)

    def is_compatible(self) -> bool:
        return self.mapping_plan.is_compatible()

    def verify_integrity(self, expected_schema_digest: str | None = None) -> bool:
        """Verify the cached profile, full plan hash, and schema binding."""
        if expected_schema_digest and self.remote_schema_digest != expected_schema_digest:
            return False
        if self.mapping_plan.remote_schema_digest != self.remote_schema_digest:
            return False
        expected_plan_hash = self.mapping_plan.plan_hash()
        if not hmac.compare_digest(expected_plan_hash, self.plan_hash):
            return False
        expected_profile_hash = self._hash_profile(
            self.remote_endpoint,
            self.remote_transport,
            self.remote_schema_digest,
            expected_plan_hash,
            self.timestamp_utc,
            self.remote_stdio_command,
        )
        return hmac.compare_digest(expected_profile_hash, self.profile_hash)

    @staticmethod
    def _hash_profile(
        endpoint: str,
        transport: str,
        schema_digest: str,
        plan_hash: str,
        timestamp: str,
        stdio_command: tuple[str, ...] = (),
    ) -> str:
        payload = {
            "remote_endpoint": endpoint,
            "remote_transport": transport,
            "remote_schema_digest": schema_digest,
            "plan_hash": plan_hash,
            "timestamp_utc": timestamp,
            "remote_stdio_command": list(stdio_command),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @classmethod
    def build(
        cls,
        probe: ProbeResult,
        plan: ProtocolMappingPlan,
    ) -> ProtocolProfile:
        plan_hash = plan.plan_hash()
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        profile_hash = cls._hash_profile(
            probe.mcp_endpoint,
            probe.transport.value,
            plan.remote_schema_digest,
            plan_hash,
            ts,
            probe.stdio_command,
        )
        return cls(
            remote_endpoint=probe.mcp_endpoint,
            remote_transport=probe.transport.value,
            remote_schema_digest=plan.remote_schema_digest,
            mapping_plan=plan,
            probe_latency_ms=probe.latency_ms,
            plan_hash=plan_hash,
            profile_hash=profile_hash,
            timestamp_utc=ts,
            remote_stdio_command=probe.stdio_command,
            agent_model=plan.agent_model,
            agent_version=plan.agent_version,
            probe_notes=probe.probe_notes,
        )

    @classmethod
    def native(cls, endpoint: str = "http://localhost:8000") -> ProtocolProfile:
        """Native identity profile for a canonical local server."""
        from cop_worker.protocol.transport_probe import ProbeResult, TransportType

        probe = ProbeResult(
            transport=TransportType.STREAMABLE_HTTP,
            base_url=endpoint,
            mcp_endpoint=f"{endpoint}/mcp",
            latency_ms=0.0,
            probe_notes="native",
        )
        plan = ProtocolMappingPlan.native_plan()
        return cls.build(probe, plan)


from cop_worker.protocol.profile_cache import ProfileCache  # noqa: E402,F401  (re-export)
