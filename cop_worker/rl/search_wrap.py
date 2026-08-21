"""Serving entry point: wrap a loaded RL policy in the minimax-first adapter."""

from __future__ import annotations

from cop_worker.rl.search_policy import SearchRolePolicy


def wrap_with_search(
    policy,
    role: str,
    terms: dict | None = None,
    *,
    depth: int = 4,
    belief_mode: bool = False,
    scent_model: str = "",
):
    """Wrap a loaded RL policy in the minimax-first adapter (serving entry point).

    Depth 4 measured 2026-08-10: cop d4 captures thief d4 4/4 (mean step 18) at
    ~3s/half-move — decisive and far inside the 180s turn budget; thief d4 survives
    every non-search cop tested. Lower to 3 only if latency ever becomes a concern.

    ``scent_model`` is the pairing's locked model: under ``multiplicative_book_v1``
    the search decodes the clamped book field (exact inverse) so it stays sighted;
    any other value keeps the chebyshev-only resolution byte-identical.
    """
    terms = terms or {}
    return SearchRolePolicy(
        "cop" if role in {"police", "cop"} else "thief",
        depth=depth,
        fallback=policy,
        max_steps=int(terms.get("max_steps", 35)),
        barriers_max=int(terms.get("barriers_max", 14)),
        belief_mode=belief_mode,
        decode_book_scent=(scent_model == "multiplicative_book_v1"),
    )
