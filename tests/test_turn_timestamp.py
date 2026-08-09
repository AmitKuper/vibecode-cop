"""Every turn we send must carry a non-empty ISO-8601 timestamp.

``build_turn`` used to default ``timestamp`` to ``""`` and no caller passed one, so every turn
on the wire went out with an empty stamp. At least one live peer (imreeyal, brief section 3.3)
refuses an empty stamp *at validation, before any state change* -- which would have turned all
six sub-games into technical losses without a single line of our code failing.

The stamp must also stay OUT of the commit preimage: it is per-send wall-clock, so folding it
into the sealed payload would make a re-sent turn hash differently and read as tampering.
"""

from __future__ import annotations

from datetime import datetime

from cop_worker.protocol.reference_v3 import build_turn, reference_commit

PAYLOAD = {
    "step": 3,
    "role": "thief",
    "sub_game": 1,
    "position": [3, 3],
    "move": "N",
    "intent": "truth",
    "barrier_placed": None,
}
NONCE = "0" * 32


def _turn(**kwargs):
    turn, record = build_turn(
        record_payload=dict(PAYLOAD),
        nonce=NONCE,
        sender="thief",
        hint="heading north",
        smell_grid={"3,3": 0.9},
        **kwargs,
    )
    return turn, record


def test_timestamp_defaults_to_a_parseable_iso_utc_stamp() -> None:
    turn, _ = _turn()
    assert turn["timestamp"], "an empty stamp is refused by at least one live peer"
    parsed = datetime.fromisoformat(turn["timestamp"])
    assert parsed.tzinfo is not None, "stamp must be timezone-aware (UTC), not naive"


def test_explicit_timestamp_is_preserved() -> None:
    turn, _ = _turn(timestamp="2026-08-09T18:00:00+00:00")
    assert turn["timestamp"] == "2026-08-09T18:00:00+00:00"


def test_empty_string_is_replaced_rather_than_sent() -> None:
    """A caller passing "" must not be able to reintroduce the bug."""
    turn, _ = _turn(timestamp="")
    assert turn["timestamp"]


def test_timestamp_is_not_in_the_commit_preimage() -> None:
    """Two turns stamped at different times must seal to the same commit."""
    a, rec_a = _turn(timestamp="2026-08-09T18:00:00+00:00")
    b, rec_b = _turn(timestamp="2026-08-09T19:30:00+00:00")
    assert a["timestamp"] != b["timestamp"]
    assert rec_a["commit"] == rec_b["commit"] == reference_commit(PAYLOAD, NONCE)
