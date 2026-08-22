"""Pins the reply-greeting dialect (cosmos77 pairing, 2026-08-22).

A reply-dialect peer completes Step-0 from our negotiate ack alone; a
push-dialect peer sees a strict superset of the old bare ack. The staged
greeting must be sub-game-scoped: answering sub_game 2's negotiate with
sub_game 1's greeting would be an equivocation vector, not a convenience.
"""

from __future__ import annotations

from cop_worker.protocol.reference_v3 import ReferenceV3Session, register_reference_v3_tools


class _Mcp:
    def __init__(self):
        self.tools = {}

    def tool(self, fn):
        self.tools[fn.__name__] = fn
        return fn


def _negotiate_tool(session):
    mcp = _Mcp()
    register_reference_v3_tools(mcp, session)
    return mcp.tools["negotiate"]


def _greeting(sub_game: int) -> dict:
    return {"group_id": "cosmos77", "sub_game_number": sub_game, "terms": {}, "nonce": "ab" * 16}


def _session():
    return ReferenceV3Session(lambda *a, **k: None)


def test_bare_ack_without_a_staged_greeting():
    reply = _negotiate_tool(_session())(_greeting(1))
    assert reply["ok"] is True and "message" not in reply


def test_reply_carries_the_staged_greeting_for_that_sub_game():
    session = _session()
    ours = {"group_id": "vibecode", "sub_game_number": 2, "terms": {"board_size": 7}}
    session.staged_greetings = {2: ours}
    reply = _negotiate_tool(session)(_greeting(2))
    assert reply["ok"] is True and reply["message"] is ours


def test_wrong_sub_game_gets_no_greeting():
    # sub-game scoping: sg1's negotiate must never receive sg2's greeting
    session = _session()
    session.staged_greetings = {2: {"group_id": "vibecode", "sub_game_number": 2}}
    reply = _negotiate_tool(session)(_greeting(1))
    assert reply["ok"] is True and "message" not in reply


def test_malformed_sub_game_number_stays_a_bare_ack():
    session = _session()
    session.staged_greetings = {1: {"group_id": "vibecode", "sub_game_number": 1}}
    reply = _negotiate_tool(session)({"sub_game_number": "not-a-number"})
    assert reply["ok"] is True and "message" not in reply
