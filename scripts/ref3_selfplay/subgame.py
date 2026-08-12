"""Single sub-game runner: ref-v3 commit-reveal exchange over HTTP or in-process."""

from __future__ import annotations

from ref3_selfplay.runtime import TERMS, logger
from ref3_selfplay.transport import _call_tool_http


def run_one_subgame(
    game_uid: str,
    sg: int,
    cop_ms,
    thief_ms,
    max_steps: int,
    cop_role: str,
    http_probe: dict | None = None,
) -> list[dict]:
    """Run one sub-game using ref-v3 commit-reveal message exchange.

    The cop_worker's role alternates according to ROLE_SCHEDULE.  When
    cop_worker plays 'thief', thief_worker plays 'police' (and vice-versa).
    When http_probe indicates both servers are reachable, all calls go via
    real HTTP (streamable-http transport); otherwise in-process.

    Args:
        game_uid: Series identity.
        sg: Sub-game number (1-based).
        cop_ms: cop_worker.mcp_server module (used for in-process fallback).
        thief_ms: thief_worker.mcp_server module (used for in-process fallback).
        max_steps: Number of commit steps to exchange.
        cop_role: 'police' or 'thief' — cop_worker's role in this sub-game.
        http_probe: Result of _try_real_http_probe(); if None, in-process only.

    Returns:
        List of step dicts, each with step / cop_commit / thief_commit.
    """
    thief_role = "thief" if cop_role == "police" else "police"
    use_http = (
        http_probe is not None
        and http_probe.get("cop_reachable")
        and http_probe.get("thief_reachable")
    )
    cop_url = (http_probe or {}).get("cop_url", "http://localhost:8001")
    thief_url = (http_probe or {}).get("thief_url", "http://localhost:8002")

    def _cop(tool: str, **kw: object) -> dict:
        if use_http:
            return _call_tool_http(cop_url, tool, kw)
        return getattr(cop_ms, tool)(**kw)

    def _thief(tool: str, **kw: object) -> dict:
        if use_http:
            return _call_tool_http(thief_url, tool, kw)
        return getattr(thief_ms, tool)(**kw)

    # --- Start both gamelets ---
    _cop(
        "start_gamelet",
        game_uid=game_uid,
        sub_game_number=sg,
        terms=TERMS,
        opponent_group="ref3_peer",
        role=cop_role,
    )
    _thief(
        "start_gamelet",
        game_uid=game_uid,
        sub_game_number=sg,
        terms=TERMS,
        opponent_group="ref3_peer",
        role=thief_role,
    )

    # --- Transition to PLAYING ---
    _cop("start_playing", game_uid=game_uid, sub_game_number=sg)
    _thief("start_playing", game_uid=game_uid, sub_game_number=sg)

    cop_status = _cop("get_status", game_uid=game_uid, sub_game_number=sg)
    thief_status = _thief("get_status", game_uid=game_uid, sub_game_number=sg)
    logger.info(
        "SG%d cop_state=%s thief_state=%s cop_role=%s thief_role=%s transport=%s",
        sg,
        cop_status["state"],
        thief_status["state"],
        cop_role,
        thief_role,
        "HTTP" if use_http else "in-process",
    )

    step_log: list[dict] = []
    commit_payload = {
        "step": 0,
        "kind": "commit",
        "commitment_hash": "0" * 64,
        "nonce": None,
        "action": None,
    }

    for step in range(1, max_steps + 1):
        # --- ref-v3 commit exchange ---
        commit_payload["step"] = step
        cop_resp = _cop(
            "deliver_event",
            game_uid=game_uid,
            sub_game_number=sg,
            event_type="opponent_turn",
            payload=dict(commit_payload),
        )
        cop_hash = cop_resp.get("response_payload", {}).get("commitment_hash", "0" * 64)

        commit_payload["commitment_hash"] = cop_hash
        thief_resp = _thief(
            "deliver_event",
            game_uid=game_uid,
            sub_game_number=sg,
            event_type="opponent_turn",
            payload=dict(commit_payload),
        )
        thief_hash = thief_resp.get("response_payload", {}).get("commitment_hash", "0" * 64)
        commit_payload["commitment_hash"] = thief_hash

        entry = {
            "step": step,
            "cop_commit": cop_hash[:16],
            "thief_commit": thief_hash[:16],
        }
        step_log.append(entry)
        print(f"    step {step:2d}/{max_steps}  cop={cop_hash[:12]}…  thief={thief_hash[:12]}…")

    # --- Shutdown both gamelets ---
    _cop("shutdown_gamelet", game_uid=game_uid, sub_game_number=sg)
    _thief("shutdown_gamelet", game_uid=game_uid, sub_game_number=sg)

    return step_log
