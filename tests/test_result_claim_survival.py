"""The audit claim must describe the GAME's ending, never the exchange's.

Regression pin for the najamjad finding (2026-08-14): a thief that survived the
step limit used to submit result_claim="timeout" while our own filed result row
said "survival". Peers that treat a contradicted ending as a dispute then set
mutual_agreement.confirmed=false while ours said true — two counted files
disagreeing about agreement itself is what rules 33-35 void a match for.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ref3_match.subgame_turns import result_claim  # noqa: E402


def test_no_capture_claims_survival_not_timeout():
    assert result_claim(False) == "survival"


def test_capture_claims_capture():
    assert result_claim(True) == "capture"


@pytest.mark.parametrize("captured", [True, False])
def test_claim_is_in_the_reference_v3_vocabulary(captured):
    """The set the session validator enforces, read from its source so it stays honest."""
    import re

    import cop_worker.protocol.reference_v3.session as sess

    src = Path(sess.__file__).read_text(encoding="utf-8")
    allowed = set(re.findall(r'"(capture|survival|timeout|technical_loss)"', src))
    assert result_claim(captured) in allowed


def test_claim_matches_the_outcome_our_result_rows_record():
    """Both sides' artifacts call a step-limit ending 'survival'; the wire must agree."""
    outcome_in_result_rows = "survival"
    assert result_claim(False) == outcome_in_result_rows
