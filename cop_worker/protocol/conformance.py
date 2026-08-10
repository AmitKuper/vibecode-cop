"""ConformanceProbes: safe pre-game protocol validation probes.

Run before any counted commitment. Tests:
- schema validation
- ping/readiness
- start-game negotiation
- idempotency behavior
- error response format
- placeholder commit/reveal structure (no real secrets)

No counted commitment occurs until all probes pass.
"""

from __future__ import annotations

import logging

from cop_worker.protocol.adapter import DeterministicProtocolAdapter
from cop_worker.protocol.conformance_probes_binding import ConformanceBindingProbesMixin
from cop_worker.protocol.conformance_probes_flow import ConformanceFlowProbesMixin
from cop_worker.protocol.conformance_remote import ConformanceRemoteMixin
from cop_worker.protocol.conformance_types import (  # noqa: F401  (public re-exports)
    _PLACEHOLDER_GAME_ID,
    ConformanceReport,
    ProbeOutcome,
    _signed_placeholder_envelope,
)
from cop_worker.protocol.mapping_plan import ProtocolMappingPlan

logger = logging.getLogger(__name__)


class ConformanceProbes(
    ConformanceRemoteMixin,
    ConformanceBindingProbesMixin,
    ConformanceFlowProbesMixin,
):
    """Run safe, non-mutating probes against the DeterministicProtocolAdapter."""

    def __init__(self, adapter: DeterministicProtocolAdapter, plan: ProtocolMappingPlan) -> None:
        self._adapter = adapter
        self._plan = plan

    def run_all(self) -> ConformanceReport:
        probes = [
            self._probe_schema_validation,
            self._probe_field_mapping_completeness,
            self._probe_commitment_binding,
            self._probe_nonce_isolation,
            self._probe_protected_field_integrity,
            self._probe_phase_ordering,
            self._probe_idempotency_structure,
            self._probe_placeholder_commit_reveal,
        ]
        results: list[ProbeOutcome] = []
        for probe_fn in probes:
            try:
                outcome = probe_fn()
                results.append(outcome)
            except Exception as exc:
                results.append(
                    ProbeOutcome(probe_name=probe_fn.__name__, passed=False, error=str(exc))
                )

        all_passed = all(p.passed for p in results)
        report = ConformanceReport(all_passed=all_passed, probes=results)
        if all_passed:
            logger.info("ConformanceProbes: all passed (%s)", report.summary())
        else:
            logger.error("ConformanceProbes: FAILED — %s", report.failed_probes())
        return report
