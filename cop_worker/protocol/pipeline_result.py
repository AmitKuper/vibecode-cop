"""Result object of the adaptive protocol negotiation."""

from __future__ import annotations

import logging

from cop_worker.protocol.adapter import DeterministicProtocolAdapter
from cop_worker.protocol.profile import ProtocolProfile

logger = logging.getLogger(__name__)


class AdaptiveNegotiationResult:
    def __init__(
        self,
        profile: ProtocolProfile,
        adapter: DeterministicProtocolAdapter,
        cache_hit: bool = False,
    ) -> None:
        self.profile = profile
        self.adapter = adapter
        self.cache_hit = cache_hit

    @property
    def profile_hash(self) -> str:
        return self.profile.profile_hash

    @property
    def plan_hash(self) -> str:
        return self.profile.plan_hash

    @property
    def is_compatible(self) -> bool:
        return self.profile.is_compatible()
