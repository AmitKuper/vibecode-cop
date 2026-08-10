"""ProtocolProfile serialization and disk persistence (mixin)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from cop_worker.protocol.mapping_plan import ProtocolMappingPlan
from cop_worker.reliability.durable_io import atomic_write_json

if TYPE_CHECKING:  # pragma: no cover - typing only
    from cop_worker.protocol.profile import ProtocolProfile


class ProfileSerdeMixin:
    """to/from dict, save/load."""

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
