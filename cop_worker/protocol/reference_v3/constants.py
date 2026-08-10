"""Dialect constants, tool names, scent locks, terms keys, and error types."""

from __future__ import annotations

REFERENCE_V3_DIALECT = "copthief-league-reference-v3"
REFERENCE_V3_TOOLS = {
    "negotiate": "message",
    "receive_turn": "message",
    "submit_audit": "payload",
    "receive_control": "message",
}
REFERENCE_V3_WIRE_LOCK = "229ae6487a418c3fcb6da9be404de2f2533c288ebc228811bff6dedc4164d6f7"
REFERENCE_V3_SCENT_LOCK = "934c220d5bf62acaa3297c6c9d723ea954c220260b02292ca17f6d5daef9f4d9"
# Both registered scent-model doc hashes, recomputed from the kit's own generator at every
# commit from first registration (9f34b04) through origin/main (be96e57) — declaring any
# other value for the same model is itself a Step-0 refusal under the kit's truth table.
SCENT_LOCKS = {
    "multiplicative_book_v1": REFERENCE_V3_SCENT_LOCK,
    "subtractive_chebyshev_v1": "81ebee59640e80eae8ca9ee5f86abd26e7edf5cdbb27d15925cb6ee45ca6ddf4",
}

TERMS_KEYS = (
    "board_size",
    "smell_grid_size",
    "decay_per_step",
    "emit_intensity",
    "min_center_intensity",
    "max_steps",
    "barriers_max",
    "setting",
    "hint_max_words",
    "axis_origin_corner",
    "axis_start_index",
    "thief_start",
    "cop_start",
    "num_games",
)


class ReferenceV3Error(ValueError):
    """A deterministic refusal of an incompatible or invalid reference-v3 message."""


class ReferenceV3EquivocationError(ReferenceV3Error):
    """A played step was resent under a different commitment."""
