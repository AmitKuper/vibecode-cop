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
from pathlib import Path

from agent.adaptive.mapping_plan import ProtocolMappingPlan
from agent.adaptive.transport_probe import ProbeResult
from agent.reliability.durable_io import atomic_write_json


@dataclass
class ProtocolProfile:
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

    def to_dict(self) -> dict:
        return {
            "remote_endpoint": self.remote_endpoint,
            "remote_transport": self.remote_transport,
            "remote_schema_digest": self.remote_schema_digest,
            "mapping_plan": self.mapping_plan.to_dict(),
            "probe_latency_ms": self.probe_latency_ms,
            "plan_hash": self.plan_hash,
            "profile_hash": self.profile_hash,
            "timestamp_utc": self.timestamp_utc,
            "remote_stdio_command": list(self.remote_stdio_command),
            "agent_model": self.agent_model,
            "agent_version": self.agent_version,
            "probe_notes": self.probe_notes,
            "compatible_fixtures_passed": self.compatible_fixtures_passed,
            "incompatible_fixtures_rejected": self.incompatible_fixtures_rejected,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ProtocolProfile:
        return cls(
            remote_endpoint=d["remote_endpoint"],
            remote_transport=d["remote_transport"],
            remote_schema_digest=d["remote_schema_digest"],
            mapping_plan=ProtocolMappingPlan.from_dict(d["mapping_plan"]),
            probe_latency_ms=d.get("probe_latency_ms", 0.0),
            plan_hash=d["plan_hash"],
            profile_hash=d["profile_hash"],
            timestamp_utc=d.get("timestamp_utc", ""),
            remote_stdio_command=tuple(d.get("remote_stdio_command", ())),
            agent_model=d.get("agent_model", "unknown"),
            agent_version=d.get("agent_version", "1.0"),
            probe_notes=d.get("probe_notes", ""),
            compatible_fixtures_passed=d.get("compatible_fixtures_passed", []),
            incompatible_fixtures_rejected=d.get("incompatible_fixtures_rejected", []),
        )

    def save(self, path: Path) -> None:
        atomic_write_json(path, self.to_dict())

    @classmethod
    def load(cls, path: Path) -> ProtocolProfile:
        return cls.from_dict(json.loads(path.read_text()))

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
        from agent.adaptive.transport_probe import ProbeResult, TransportType

        probe = ProbeResult(
            transport=TransportType.STREAMABLE_HTTP,
            base_url=endpoint,
            mcp_endpoint=f"{endpoint}/mcp",
            latency_ms=0.0,
            probe_notes="native",
        )
        plan = ProtocolMappingPlan.native_plan()
        return cls.build(probe, plan)


class ProfileCache:
    """Cache ProtocolProfile by remote schema digest. Invalidate on digest change."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache: dict[str, ProtocolProfile] = {}
        self._cache_dir = cache_dir

    def get(self, schema_digest: str) -> ProtocolProfile | None:
        if schema_digest in self._cache:
            profile = self._cache[schema_digest]
            return profile if profile.verify_integrity(schema_digest) else None
        if self._cache_dir:
            p = self._cache_dir / f"profile_{schema_digest[:16]}.json"
            if p.exists():
                try:
                    profile = ProtocolProfile.load(p)
                    if not profile.verify_integrity(schema_digest):
                        return None
                    self._cache[schema_digest] = profile
                    return profile
                except Exception:
                    pass
        return None

    def put(self, profile: ProtocolProfile) -> None:
        self._cache[profile.remote_schema_digest] = profile
        if self._cache_dir:
            p = self._cache_dir / f"profile_{profile.remote_schema_digest[:16]}.json"
            profile.save(p)

    def invalidate(self, schema_digest: str) -> None:
        self._cache.pop(schema_digest, None)
