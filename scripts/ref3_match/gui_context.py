"""Turn-loop facts for the live GUI - this side's local truth only.

The turn loop calls the note_* helpers at its natural boundaries (window start,
peer turn absorbed, our turn sealed, window settled); publish_view merges the
latest facts into every SafeLiveView. All values are local truth - hint text,
commit PREFIXES, window/score/audit bookkeeping - never a hidden coordinate,
and every path is a guarded no-op when no GUI is registered.
"""

from __future__ import annotations

from ref3_match import gui_bridge

#: Latest turn-loop facts; written only via set_turn_context().
_CTX: dict = {}


def set_turn_context(**facts) -> None:
    """Merge turn-loop facts (hint, your_turn, commits, window, score, audits).

    No-op when no GUI is registered; never raises. Commit values are truncated
    to 12-char prefixes here so full hashes never sit in GUI state.
    """
    if gui_bridge._VIEW_MODEL is None:
        return
    try:
        for key in ("last_commit_sent", "last_commit_received"):
            if isinstance(facts.get(key), str):
                facts[key] = facts[key][:12]
        _CTX.update({k: v for k, v in facts.items() if v is not None})
    except Exception:  # the GUI must never be able to touch play
        return


def note_window(sub_game: int, opponent_group: str, terms: dict) -> None:
    """Window start: pin the header facts (one call from the handshake path)."""
    set_turn_context(
        sub_game=sub_game,
        opponent_group=opponent_group,
        max_steps=int((terms or {}).get("max_steps", 35)),
        num_sub_games=int((terms or {}).get("num_games", 6)),
        protocol_state="GAMEPLAY",
    )


def note_received(opp: dict, step: int) -> None:
    """Peer turn absorbed: their hint + commit; the banner turns YOUR TURN."""
    set_turn_context(
        step=step,
        last_hint=str((opp or {}).get("hint", "")),
        last_commit_received=str((opp or {}).get("commit", "")),
        your_turn=True,
    )


def note_sent(out_session) -> None:
    """Our sealed turn is out: banner LOCKED until the turn returns."""
    try:
        commit = (out_session.local_records or [{}])[-1].get("commit", "")
    except Exception:
        commit = ""
    set_turn_context(your_turn=False, last_commit_sent=str(commit))


def note_settled(sub_game: int, ok: bool, outcome: str, role: str) -> None:
    """Audit verdict for this role's window: extend the ticker + running score."""
    if gui_bridge._VIEW_MODEL is None:
        return
    try:
        audits = dict(_CTX.get("audit_map", {}))
        audits[int(sub_game)] = "ok" if ok else "failed"
        cop_s, thief_s = (20, 5) if outcome == "capture" else (5, 10)
        us, them = (cop_s, thief_s) if role == "police" else (thief_s, cop_s)
        score = dict(_CTX.get("score", {"cop": 0, "thief": 0}))
        score["cop" if role == "police" else "thief"] += us
        score["thief" if role == "police" else "cop"] += them
        set_turn_context(
            audit_map=audits,
            audits=tuple(audits.get(i, "") for i in range(1, max(audits) + 1)),
            score=score,
            protocol_state="SETTLED",
        )
    except Exception:
        return
