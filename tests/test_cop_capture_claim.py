"""The cop must be able to INITIATE a capture settlement, and corroborate what it accepts.

Before this change our cop only ever *answered* concessions: it never emitted
``capture_claim``, so against a thief that (like ours) only answers claims, no co-location
capture could settle in either direction. The reference peer's own policy — claim your own
cell every turn (kit turnloop.py:169) — is adopted verbatim. A ``caught=true`` is settled
but classified (answer vs concession, SPEC §3.1) and corroborated against OUR barrier
record; failure records a disputed capture rather than a clean one.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from live_match_ref3 import (  # noqa: E402
    _absorb_inbound_caught,
    _compose_and_send_turn,
    _corroborate_caught,
    _refine_disputed_trail,
    _settle,
)


class TestCorroborateCaught:
    def test_answer_echoing_our_claim_is_clean(self) -> None:
        kind, clean = _corroborate_caught([3, 3], [3, 3], [], [3, 3], 7)
        assert (kind, clean) == ("answer", True)

    def test_concession_on_our_barrier_is_clean_rule46(self) -> None:
        kind, clean = _corroborate_caught([2, 4], None, [[2, 4]], [0, 0], 7)
        assert (kind, clean) == ("concession", True)

    def test_concession_boxed_by_our_barriers_is_clean_rule47(self) -> None:
        kind, clean = _corroborate_caught([0, 0], None, [[1, 0], [0, 1]], [5, 5], 7)
        assert (kind, clean) == ("concession", True)

    def test_concession_with_an_open_neighbour_is_disputed(self) -> None:
        kind, clean = _corroborate_caught([3, 3], None, [[3, 2]], [0, 0], 7)
        assert (kind, clean) == ("concession", False)

    def test_thief_reported_barriers_never_corroborate(self) -> None:
        # Corroboration uses OUR record only — an empty own-record with a fully
        # "boxed" cell claimed by the thief stays disputed.
        kind, clean = _corroborate_caught([3, 3], None, [], [0, 0], 7)
        assert (kind, clean) == ("concession", False)

    def test_malformed_cell_is_disputed(self) -> None:
        assert _corroborate_caught("3,3", None, [], [0, 0], 7) == ("malformed", False)


class TestClaimEmissionCallSites:
    """Source-level pins: the loop actually claims, settles, and corroborates."""

    def test_cop_claims_its_own_cell_every_turn(self) -> None:
        # Turn composition lives in _compose_and_send_turn since the ref3_match split.
        src = inspect.getsource(_compose_and_send_turn)
        # The claim travels in the kit's wire convention [row, col] — our internal
        # [x, y] transposed. Sending [x, y] raw registered our cells TRANSPOSED in
        # the peer's physics (live finding, 2026-08-10 rehearsal).
        assert 'capture_claim = _to_wire_cell(mover.pos) if role == "police" else None' in src
        assert "capture_claim=capture_claim" in src

    def test_settlement_corroborates_before_recording(self) -> None:
        # Inbound caught=true handling lives in _absorb_inbound_caught; the audit-time
        # trail-end refinement in _refine_disputed_trail (degrades: notes, never accuses).
        src = inspect.getsource(_absorb_inbound_caught)
        assert "_corroborate_caught" in src
        assert "disputed_capture" in src
        assert "trail_end_mismatch" in inspect.getsource(_refine_disputed_trail)

    def test_summary_carries_the_disputed_flag(self) -> None:
        src = inspect.getsource(_settle)
        assert '"disputed_capture": disputed_capture' in src
