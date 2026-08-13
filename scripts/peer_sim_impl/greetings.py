"""Step-0 greetings: full form for our own verification, najamjad's LEAN wire form.

Real peers do not send our full greeting shape. najamjad's negotiate carries only
``terms, nonce, signature, role, sub_game_number, game_uid, identity,
scent_model_sha256, info_mode_sha256`` — no top-level ``group_id`` and no
``wire_shape_sha256``. We build with our own helper (guaranteeing terms/uid
parity) and then strip down to that exact key set.
"""

from __future__ import annotations

import hashlib
import secrets

from cop_worker.protocol.reference_v3 import build_negotiation, default_terms

GROUP_ID = "peersim01"  # 8 chars; sorts before "vibecode" -> peersim cop on odd windows
OPP_GROUP = "vibecode"
SCENT_MODEL = "subtractive_chebyshev_v1"
#: najamjad also declares an information-mode lock; the value is the peer's own.
INFO_MODE_SHA = hashlib.sha256(b"peersim-info-mode-v1").hexdigest()
LEAN_KEYS = (
    "terms",
    "nonce",
    "signature",
    "role",
    "sub_game_number",
    "game_uid",
    "identity",
    "scent_model_sha256",
)


def role_for(window: int) -> str:
    """peersim01 sorts before vibecode: cop on windows 1/3/5, thief on 2/4/6."""
    return "police" if window % 2 == 1 else "thief"


def make_terms(profile: str) -> dict:
    """The exact terms vibecode signs: base constitution + the profile's setting."""
    from cop_worker.config_loader import load_game

    setting = load_game(profile).get("world", {}).get("map_area", "New York")
    return default_terms({"setting": setting})


def _identity() -> dict:
    return {
        "group_id": GROUP_ID,
        "group_name": GROUP_ID,
        "llm_model": "none (peersim template hints; scripted movement)",
        "members": ["Peer Simulator"],
    }


def make_greetings(terms: dict) -> dict[int, tuple[dict, dict]]:
    """Pre-generate a stable (full, lean) greeting pair per window.

    Stability matters: the eager quirk sends window N+1's greeting early and the
    duplicate quirk re-sends window N's — every copy must carry identical bytes
    so vibecode's greeting relay and dedupe see ONE agreement, not equivocation.
    """
    out: dict[int, tuple[dict, dict]] = {}
    for window in range(1, 7):
        full = build_negotiation(
            terms=terms,
            nonce=secrets.token_hex(16),
            group_id=GROUP_ID,
            group_name=GROUP_ID,
            role=role_for(window),
            sub_game_number=window,
            opponent_group=OPP_GROUP,
            identity=_identity(),
            scent_model=SCENT_MODEL,
        )
        lean = {key: full[key] for key in LEAN_KEYS}
        lean["info_mode_sha256"] = INFO_MODE_SHA
        out[window] = (full, lean)
    return out
