"""Identify WHICH registered scent model a peer is transmitting, from its wire frames.

The reference-v3 registry (external kit ``vectors/locked_model.json``) holds two PROMOTED
``scent_model`` docs, and the kit's own ``scent_book_v3.json::divergence_vs_reference`` notes
they "differ in shape AND support, so a team can see at a glance which model it built":

===========================  ==========================================  ================
model                        distinct values around an isolated emitter  declared sha256
===========================  ==========================================  ================
``subtractive_chebyshev_v1`` {0.3, 0.6, 0.9} -- flat Chebyshev rings      81ebee59...
``multiplicative_book_v1``   {0.04, 0.14, 0.2, 0.42, 0.62, 0.9}          934c220d...
===========================  ==========================================  ================

We implement and declare ``multiplicative_book_v1`` (``RulesEngine.update_scent``,
``REFERENCE_V3_SCENT_LOCK``). A peer running the other model is not "wrong" -- the kit calls
them "different registrations" -- but our cop would then be reading a field whose scale and
falloff it was never trained on, and neither side would notice: the kit's refusal rule is
"ONLY when both peers declare a family and disagree -- omission is never refusal", so an
undeclared mismatch passes the mutual audit silently. That is exactly what happened in the
2026-08-08 friendlies: neither side declared ``scent_model_sha256``.

This module reads it off the wire instead of trusting a declaration.
"""

from __future__ import annotations

# Emission values each model can put on a cell, taken from the kit's divergence vectors.
_BOOK_VALUES = frozenset({0.04, 0.14, 0.2, 0.42, 0.62, 0.9})
_CHEBYSHEV_VALUES = frozenset({0.3, 0.6, 0.9})

# Values that only one model can ever produce on a FRESH field -- the decisive evidence.
_BOOK_ONLY = _BOOK_VALUES - _CHEBYSHEV_VALUES
_CHEBYSHEV_ONLY = _CHEBYSHEV_VALUES - _BOOK_VALUES

BOOK_SHA256 = "934c220d5bf62acaa3297c6c9d723ea954c220260b02292ca17f6d5daef9f4d9"
CHEBYSHEV_SHA256 = "81ebee59640e80eae8ca9ee5f86abd26e7edf5cdbb27d15925cb6ee45ca6ddf4"

_TOLERANCE = 1e-6


def _matches(value: float, allowed: frozenset[float]) -> bool:
    return any(abs(value - a) <= _TOLERANCE for a in allowed)


def fingerprint(smell_grid: dict[str, float]) -> dict:
    """Classify one transmitted ``{"r,c": intensity}`` frame.

    Accumulated frames are ambiguous by design -- both models decay, so a late frame holds
    arbitrary intermediate values. Only *model-exclusive* emission values are treated as
    evidence, so a late frame degrades to ``"inconclusive"`` rather than guessing.

    Returns a dict with ``model`` in ``{"multiplicative_book_v1", "subtractive_chebyshev_v1",
    "inconclusive", "empty"}`` plus the supporting counts.
    """
    values = [float(v) for v in (smell_grid or {}).values() if float(v) > 0.0]
    if not values:
        return {
            "model": "empty",
            "cells": 0,
            "max": None,
            "book_only_hits": 0,
            "chebyshev_only_hits": 0,
            "note": "peer transmitted no positive scent cells",
        }

    book_only = sum(1 for v in values if _matches(v, _BOOK_ONLY))
    cheb_only = sum(1 for v in values if _matches(v, _CHEBYSHEV_ONLY))

    if book_only and not cheb_only:
        model = "multiplicative_book_v1"
    elif cheb_only and not book_only:
        model = "subtractive_chebyshev_v1"
    else:
        model = "inconclusive"

    return {
        "model": model,
        "cells": len(values),
        "max": round(max(values), 6),
        "distinct": sorted({round(v, 6) for v in values})[:12],
        "book_only_hits": book_only,
        "chebyshev_only_hits": cheb_only,
        "sha256": {
            "multiplicative_book_v1": BOOK_SHA256,
            "subtractive_chebyshev_v1": CHEBYSHEV_SHA256,
        }.get(model),
    }


def agrees_with_us(smell_grid: dict[str, float]) -> bool | None:
    """True/False when the frame is decisive, None when inconclusive or empty.

    We run ``multiplicative_book_v1``, so agreement means the peer does too.
    """
    model = fingerprint(smell_grid)["model"]
    if model in ("inconclusive", "empty"):
        return None
    return model == "multiplicative_book_v1"
