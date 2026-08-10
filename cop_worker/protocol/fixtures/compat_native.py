"""Compatible fixture: the canonical single `action` tool."""

from __future__ import annotations

from cop_worker.protocol.fixtures.base import Fixture
from cop_worker.protocol.fixtures.helpers import _intro, _native_plan, _tool


def fixture_native_action() -> Fixture:
    tools = [
        _tool(
            "action",
            "Send a game action",
            {
                "game_id": "string",
                "step": "integer",
                "role": "string",
                "phase": "string",
                "commitment": "string",
                "move": "string",
                "nonces": "object",
                "config_sha256": "string",
                "timestamp": "string",
            },
        )
    ]
    return Fixture(
        name="native_action",
        description="Canonical single action tool — identity mapping",
        compatible=True,
        introspection=_intro("native", tools),
        expected_plan=_native_plan(),
    )
