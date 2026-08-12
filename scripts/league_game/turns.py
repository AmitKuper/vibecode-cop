"""Per-sub-game commit exchange loop for the in-process league runner."""

from __future__ import annotations

import hashlib
import secrets


def _run_turn_loop(cop_ms, thief_ms, game_uid: str, sg: int, max_steps: int) -> None:
    # Turn loop — use max_steps (not clamped) for actual number of steps played
    actual_steps = max_steps
    for step in range(1, actual_steps + 1):
        cop_commit = hashlib.sha256(secrets.token_bytes(16)).hexdigest()
        thief_commit = hashlib.sha256(secrets.token_bytes(16)).hexdigest()

        # Send cop's commit to thief
        thief_ms.deliver_event(
            game_uid,
            sg,
            "opponent_turn",
            {
                "step": step,
                "kind": "commit",
                "commitment_hash": cop_commit,
                "nonce": None,
                "action": None,
            },
        )

        # Send thief's commit to cop
        cop_ms.deliver_event(
            game_uid,
            sg,
            "opponent_turn",
            {
                "step": step,
                "kind": "commit",
                "commitment_hash": thief_commit,
                "nonce": None,
                "action": None,
            },
        )

        print(f"  Step {step}/{actual_steps}  cop={cop_commit[:8]}  thief={thief_commit[:8]}")
