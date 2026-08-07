"""Fake worker MCP server for LeagueManager tests.

All 6 tools return hardcoded deterministic responses.
No game logic. No network. No subprocess.
"""

from __future__ import annotations


class MockWorker:
    """In-process fake for one worker (cop or thief).

    LM tests inject this instead of calling a real MCP server.
    """

    def __init__(self, role: str = "police") -> None:
        """Initialise mock worker with given role."""
        self.role = role
        self.gamelets: dict = {}
        self.calls: list = []

    def start_gamelet(
        self, game_uid: str, sub_game_number: int, terms: dict, opponent_group: str, role: str
    ) -> dict:
        """Record call and create a fake gamelet entry."""
        self.calls.append(("start_gamelet", game_uid, sub_game_number))
        self.gamelets[(game_uid, sub_game_number)] = {"state": "LOCKED", "step": 0}
        return {"ok": True}

    def deliver_event(
        self, game_uid: str, sub_game_number: int, event_type: str, payload: dict
    ) -> dict:
        """Record call and return a fake deliver response."""
        self.calls.append(("deliver_event", game_uid, sub_game_number, event_type))
        return {"ok": True, "response_payload": {"ack": True}, "state": "PLAYING"}

    def get_status(self, game_uid: str, sub_game_number: int) -> dict:
        """Record call and return fake status."""
        self.calls.append(("get_status", game_uid, sub_game_number))
        state = self.gamelets.get((game_uid, sub_game_number), {}).get("state", "CREATED")
        return {
            "game_uid": game_uid,
            "sub_game_number": sub_game_number,
            "state": state,
            "step": 0,
            "role": self.role,
        }

    def prepare_audit(self, game_uid: str, sub_game_number: int) -> dict:
        """Record call and return fake audit bundle."""
        self.calls.append(("prepare_audit", game_uid, sub_game_number))
        key = (game_uid, sub_game_number)
        if key in self.gamelets:
            self.gamelets[key]["state"] = "AUDITING"
        return {
            "ok": True,
            "audit_bundle": {
                "game_uid": game_uid,
                "sub_game_number": sub_game_number,
                "role": self.role,
                "steps": [],
                "terminal_condition": "capture",
                "final_step": 10,
                "log_hash": "deadbeef" * 8,
            },
        }

    def get_result(self, game_uid: str, sub_game_number: int) -> dict:
        """Record call and return fake result."""
        self.calls.append(("get_result", game_uid, sub_game_number))
        return {
            "game_uid": game_uid,
            "sub_game_number": sub_game_number,
            "result_claim": "capture",
            "winner": "police",
            "audit_ok": True,
            "audit_summary": {
                "steps_verified": 10,
                "steps_tampered": 0,
                "verification_status": "VERIFIED",
            },
            "log_hash": "deadbeef" * 8,
            "artifact_path": f"/tmp/log_{game_uid}_g{sub_game_number:02d}.json",
            "llm_tokens": {"prompt": 100, "completion": 50, "total": 150},
            "final_step": 10,
        }

    def shutdown_gamelet(self, game_uid: str, sub_game_number: int) -> dict:
        """Record call and return fake shutdown response."""
        self.calls.append(("shutdown_gamelet", game_uid, sub_game_number))
        return {"ok": True, "final_state": "ABORTED"}

    def assert_called(self, tool_name: str) -> None:
        """Assert that the given tool was called at least once."""
        names = [c[0] for c in self.calls]
        assert tool_name in names, f"Expected {tool_name!r} to be called, got: {names}"

    def reset(self) -> None:
        """Clear all recorded calls and gamelet state."""
        self.calls.clear()
        self.gamelets.clear()
