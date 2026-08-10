"""Self-check against the kit's frozen core vectors."""

from __future__ import annotations

from typing import Any

from cop_worker.protocol.reference_v3.constants import ReferenceV3Error
from cop_worker.protocol.reference_v3.hashing import reference_commit


def assert_core_vectors() -> None:
    """Fail closed if this interpreter cannot reproduce the kit's published CORE vectors."""
    cases: list[tuple[dict[str, Any], str, str]] = [
        (
            {
                "step": 0,
                "type": "system_spec",
                "spec": {"os": "Linux", "cpu_cores": 4, "ram_gb": 16.0, "vram_gb": 0.0},
                "model": "cli-default",
                "code_version": "1.0",
                "group_name": "Example-Team",
                "sub_game_number": 1,
            },
            "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
            "69c9a786d18829990291cd0ffb768eacfa009011b0c89a6f4f32330551e2003e",
        ),
        (
            {
                "step": 2,
                "state": "grid=7x7;self=[2, 4];barriers=[[1, 1]]",
                "position": [2, 4],
                "move": "MOVE:N",
                "intent": "lie",
                "hint": "אני ליד הכיכר 🙂",
            },
            "deadbeefcafef00dfeedface00c0ffee",
            "2caaeb0a7e656868b85166a9ebe34226bae4fdcb79cb7a0a23759121769d9338",
        ),
    ]
    for payload, nonce, expected in cases:
        if reference_commit(payload, nonce) != expected:
            raise ReferenceV3Error("reference-v3 CORE commit vector mismatch")
