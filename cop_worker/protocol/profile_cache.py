"""On-disk cache of negotiated protocol profiles."""

from __future__ import annotations

from pathlib import Path

from cop_worker.protocol.profile import ProtocolProfile


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
