"""Training-time switches that make the observation match what PRODUCTION actually feeds.

Two mismatches existed between training and the counted runtime. Rather than change the
runtime, these switches change *training* so the deployed policy is optimised for the
inputs it will really see:

``COPTHIEF_UNIFORM_BELIEF=1``
    Feed ``BeliefState.uniform`` every step, as ``RLMover.decide`` and
    ``Gamelet._build_obs`` do. Default training fed a live ``BeliefEngine``, so 51 of the
    201 input dims (belief heatmap + entropy + confidence) were informative in training
    and frozen at the step-1 prior in production.

``COPTHIEF_WIRE_SCENT=1``
    Accumulate scent with the wire law ``clamp(0.9*old + kernel, 0, 0.9)``
    (``RulesEngine.update_scent``) instead of the unclamped ``ScentFields`` law. The
    unclamped field grows to ~6.5 with a smooth peak at the emitter; the clamped field the
    reference-v3 wire carries saturates to a flat 0.9 plateau with the peak destroyed.

Both default OFF so existing checkpoints stay reproducible. Whatever is used for a
promoted run MUST be recorded in models/MANIFEST.json -- see :func:`describe`.
"""

from __future__ import annotations

import os

UNIFORM_BELIEF_ENV = "COPTHIEF_UNIFORM_BELIEF"
WIRE_SCENT_ENV = "COPTHIEF_WIRE_SCENT"
DECODED_SCENT_ENV = "COPTHIEF_DECODED_SCENT"
SCENT_MODEL_ENV = "COPTHIEF_SCENT_MODEL"

BOOK_MODEL = "multiplicative_book_v1"
CHEBYSHEV_MODEL = "subtractive_chebyshev_v1"
_SCENT_MODELS = {BOOK_MODEL, CHEBYSHEV_MODEL, "chebyshev", "book"}


def uniform_belief_enabled() -> bool:
    """True when training should feed the production uniform belief prior."""
    return os.environ.get(UNIFORM_BELIEF_ENV, "") == "1"


def wire_scent_enabled() -> bool:
    """True when scent should accumulate under the clamped wire law."""
    return os.environ.get(WIRE_SCENT_ENV, "") == "1"


def decoded_scent_enabled() -> bool:
    """True when the scent+belief channels carry the INVERSE of the clamped wire law.

    The negotiated wire law is unchanged by this switch -- we still transmit exactly the
    field ``multiplicative_book_v1`` prescribes. This only changes how we *read* the field
    the peer sends: ``cop_worker.scent_decoder`` recovers the emitter's cell exactly, because
    the emission kernel is injective on squared distance and the ``d2 == 8`` ring can never
    saturate. Raw clamped field: a usable peak on ~4.5% of steps. Decoded: ~100%.

    Implies ``wire_scent`` semantics: decoding an unclamped trainer field is meaningless, so
    turning this on without ``COPTHIEF_WIRE_SCENT=1`` is a configuration error.
    """
    return os.environ.get(DECODED_SCENT_ENV, "") == "1"


def scent_model() -> str:
    """The scent law this process runs — a registered model name, defaulting to the book's.

    ``COPTHIEF_SCENT_MODEL`` accepts the registered names or the shorthands
    ``book`` / ``chebyshev``. Under ``subtractive_chebyshev_v1`` the training fields and
    the serving emitter both switch to ``cop_worker.scent_chebyshev`` (rings, merge-by-max,
    subtractive decay, 0.8-peak wire snapshots); ``COPTHIEF_WIRE_SCENT`` is a book-law
    switch and is ignored in that mode. An unknown value is a configuration error — a
    silently-defaulted scent law would desynchronise physics with the Step-0 declaration.
    """
    raw = os.environ.get(SCENT_MODEL_ENV, "") or BOOK_MODEL
    if raw not in _SCENT_MODELS:
        raise ValueError(
            f"{SCENT_MODEL_ENV}={raw!r} is not a registered scent model; "
            f"expected one of {sorted(_SCENT_MODELS)}"
        )
    return CHEBYSHEV_MODEL if raw in {CHEBYSHEV_MODEL, "chebyshev"} else BOOK_MODEL


def chebyshev_scent_enabled() -> bool:
    """True when the chebyshev law governs both training fields and the serving emitter."""
    return scent_model() == CHEBYSHEV_MODEL


def describe() -> dict[str, bool | str]:
    """Observation-mode fingerprint to embed in a checkpoint/manifest entry."""
    return {
        "uniform_belief": uniform_belief_enabled(),
        "wire_scent": wire_scent_enabled(),
        "decoded_scent": decoded_scent_enabled(),
        "scent_model": scent_model(),
    }


def observation_mode_tag() -> str:
    """Short human-readable tag for run names and logs."""
    parts = []
    if uniform_belief_enabled():
        parts.append("uniformbelief")
    if wire_scent_enabled():
        parts.append("wirescent")
    if decoded_scent_enabled():
        parts.append("decodedscent")
    if chebyshev_scent_enabled():
        parts.append("chebyshev")
    return "-".join(parts) if parts else "legacy-research-obs"
