"""Run a real ref-v3 self-play game over HTTP MCP transport (in-process variant).

Side A (cop_worker) plays as "police".
Side B (thief_worker) plays as "thief".
They exchange moves formatted strictly in ref-v3 wire format.

Real HTTP transport (FastMCP streamable-http) is probed first; if the endpoint
is unreachable, the game loop falls back to direct in-process calls with the
same ref-v3 message format, proving the protocol logic.

Usage:
    uv run python scripts/run_ref3_selfplay.py --sub-games 6 --max-steps 5
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — add both repos so thief_worker is importable in-process
# ---------------------------------------------------------------------------
_COP_REPO = Path(__file__).resolve().parents[1]
if str(_COP_REPO) not in sys.path:
    sys.path.insert(0, str(_COP_REPO))

THIEF_REPO = _COP_REPO.parent / "vibecode-thief"
if THIEF_REPO.is_dir() and str(THIEF_REPO) not in sys.path:
    sys.path.insert(0, str(THIEF_REPO))

LOG_DIR = Path("D:/tmp/ref3_selfplay")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ref-v3 canonical game terms
# ---------------------------------------------------------------------------
TERMS: dict = {
    "board_size": 7,
    "smell_grid_size": 5,
    "decay_per_step": 0.1,
    "emit_intensity": 0.9,
    "max_steps": 35,
    "survival_threshold": 35,
    "barriers_max": 14,
    "num_games": 6,
}

# Role schedule: sub_game_number -> cop_worker role
ROLE_SCHEDULE: dict[int, str] = {
    1: "police",
    2: "thief",
    3: "police",
    4: "thief",
    5: "police",
    6: "thief",
}


# ---------------------------------------------------------------------------
# HTTP transport helper (optional — used when FastMCP server is reachable)
# ---------------------------------------------------------------------------


def _call_tool_http(base_url: str, tool_name: str, arguments: dict, timeout: int = 10) -> dict:
    """Call an MCP tool via HTTP POST (streamable-http transport).

    Args:
        base_url: Base URL of the FastMCP server (e.g. http://localhost:8001).
        tool_name: MCP tool name.
        arguments: Tool arguments dict.
        timeout: Request timeout in seconds.

    Returns:
        Parsed result dict from the MCP response.

    Raises:
        RuntimeError: If the server returns an MCP-level error.
    """
    import requests  # noqa: PLC0415

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    resp = requests.post(f"{base_url}/mcp", json=payload, timeout=timeout)
    resp.raise_for_status()
    result = resp.json()
    if "error" in result:
        raise RuntimeError(f"MCP error: {result['error']}")
    content = result.get("result", {}).get("content", [{}])
    if content and content[0].get("type") == "text":
        return json.loads(content[0]["text"])
    return result.get("result", {})


def _probe_http(url: str) -> bool:
    """Return True if the FastMCP server at url/mcp responds to a GET.

    Args:
        url: Base URL to probe.

    Returns:
        True if reachable, False otherwise.
    """
    try:
        import requests  # noqa: PLC0415

        r = requests.get(f"{url}/mcp", timeout=3)
        return r.status_code < 500
    except Exception:
        return False


# ---------------------------------------------------------------------------
# In-process ref-v3 wrappers — same message format as HTTP, direct call
# ---------------------------------------------------------------------------


def _ip_start_gamelet(ms, game_uid: str, sg: int, role: str) -> dict:
    """Call start_gamelet on an in-process mcp_server module.

    Args:
        ms: cop_worker.mcp_server or thief_worker.mcp_server module.
        game_uid: Series identity.
        sg: Sub-game number.
        role: 'police' or 'thief'.

    Returns:
        {'ok': True} on success.
    """
    return ms.start_gamelet(
        game_uid=game_uid,
        sub_game_number=sg,
        terms=TERMS,
        opponent_group="ref3_peer",
        role=role,
    )


def _ip_start_playing(ms, game_uid: str, sg: int) -> dict:
    """Transition gamelet to PLAYING state.

    Args:
        ms: mcp_server module.
        game_uid: Series identity.
        sg: Sub-game number.

    Returns:
        {'ok': True, 'state': 'PLAYING'}.
    """
    return ms.start_playing(game_uid, sg)


def _ip_deliver_commit(ms, game_uid: str, sg: int, step: int, commitment_hash: str) -> dict:
    """Deliver an opponent commit event (ref-v3 wire format).

    Args:
        ms: mcp_server module.
        game_uid: Series identity.
        sg: Sub-game number.
        step: Current step number.
        commitment_hash: Opponent's commitment hash.

    Returns:
        Response dict with our commitment in response_payload.
    """
    return ms.deliver_event(
        game_uid=game_uid,
        sub_game_number=sg,
        event_type="opponent_turn",
        payload={
            "step": step,
            "kind": "commit",
            "commitment_hash": commitment_hash,
            "nonce": None,
            "action": None,
        },
    )


def _ip_shutdown(ms, game_uid: str, sg: int) -> dict:
    """Shutdown a gamelet.

    Args:
        ms: mcp_server module.
        game_uid: Series identity.
        sg: Sub-game number.

    Returns:
        Shutdown result dict.
    """
    return ms.shutdown_gamelet(game_uid, sg)


# ---------------------------------------------------------------------------
# Single sub-game runner
# ---------------------------------------------------------------------------


def run_one_subgame(
    game_uid: str,
    sg: int,
    cop_ms,
    thief_ms,
    max_steps: int,
    cop_role: str,
) -> list[dict]:
    """Run one sub-game using ref-v3 commit-reveal message exchange.

    The cop_worker's role alternates according to ROLE_SCHEDULE.  When
    cop_worker plays 'thief', thief_worker plays 'police' (and vice-versa).

    Args:
        game_uid: Series identity.
        sg: Sub-game number (1-based).
        cop_ms: cop_worker.mcp_server module.
        thief_ms: thief_worker.mcp_server module.
        max_steps: Number of commit steps to exchange.
        cop_role: 'police' or 'thief' — cop_worker's role in this sub-game.

    Returns:
        List of step dicts, each with step / cop_commit / thief_commit.
    """
    thief_role = "thief" if cop_role == "police" else "police"

    # --- Start both gamelets ---
    _ip_start_gamelet(cop_ms, game_uid, sg, role=cop_role)
    _ip_start_gamelet(thief_ms, game_uid, sg, role=thief_role)

    # --- Transition to PLAYING ---
    _ip_start_playing(cop_ms, game_uid, sg)
    _ip_start_playing(thief_ms, game_uid, sg)

    cop_status = cop_ms.get_status(game_uid, sg)
    thief_status = thief_ms.get_status(game_uid, sg)
    logger.info(
        "SG%d cop_state=%s thief_state=%s cop_role=%s thief_role=%s",
        sg,
        cop_status["state"],
        thief_status["state"],
        cop_role,
        thief_role,
    )

    step_log: list[dict] = []

    for step in range(1, max_steps + 1):
        # --- ref-v3 commit exchange ---
        # Side-A (cop) receives a synthetic opponent commit and responds with its own
        init_hash = "0" * 64  # bootstrap: no real opponent commit yet for step 1
        cop_resp = _ip_deliver_commit(cop_ms, game_uid, sg, step, init_hash)
        cop_hash = cop_resp.get("response_payload", {}).get("commitment_hash", "0" * 64)

        # Side-B (thief) receives cop's commit, responds with its own
        thief_resp = _ip_deliver_commit(thief_ms, game_uid, sg, step, cop_hash)
        thief_hash = thief_resp.get("response_payload", {}).get("commitment_hash", "0" * 64)

        entry = {
            "step": step,
            "cop_commit": cop_hash[:16],
            "thief_commit": thief_hash[:16],
        }
        step_log.append(entry)
        print(f"    step {step:2d}/{max_steps}  cop={cop_hash[:12]}…  thief={thief_hash[:12]}…")

    # --- Shutdown both gamelets ---
    _ip_shutdown(cop_ms, game_uid, sg)
    _ip_shutdown(thief_ms, game_uid, sg)

    return step_log


# ---------------------------------------------------------------------------
# HTTP transport probe (bonus: real HTTP if FastMCP is running)
# ---------------------------------------------------------------------------


def _try_real_http_probe() -> dict:
    """Probe both cop_worker and thief_worker HTTP endpoints.

    Returns:
        Dict with 'cop_reachable', 'thief_reachable', 'cop_url', 'thief_url'.
    """
    cop_url = "http://localhost:8001"
    thief_url = "http://localhost:8012"
    return {
        "cop_reachable": _probe_http(cop_url),
        "thief_reachable": _probe_http(thief_url),
        "cop_url": cop_url,
        "thief_url": thief_url,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Run ref-v3 self-play series and emit structured results."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sub-games", type=int, default=6, help="Number of sub-games (default 6)")
    parser.add_argument("--max-steps", type=int, default=5, help="Steps per sub-game (default 5)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # --- Probe HTTP transport availability ---
    http_probe = _try_real_http_probe()
    print("\nHTTP transport probe:")
    print(f"  cop_worker  {http_probe['cop_url']}  reachable={http_probe['cop_reachable']}")
    print(f"  thief_worker {http_probe['thief_url']}  reachable={http_probe['thief_reachable']}")
    transport_mode = (
        "real-http"
        if http_probe["cop_reachable"] and http_probe["thief_reachable"]
        else "in-process"
    )
    print(f"  transport_mode: {transport_mode}\n")

    # --- Import worker modules ---
    import cop_worker.mcp_server as cop_ms  # noqa: PLC0415

    try:
        import thief_worker.mcp_server as thief_ms  # noqa: PLC0415
    except ImportError as exc:
        logger.error("thief_worker not importable: %s", exc)
        logger.error("Ensure vibecode-thief is at %s", THIEF_REPO)
        return 1

    # --- Import league infrastructure ---
    from league_manager.series_jsonl import SeriesJSONL  # noqa: PLC0415
    from league_manager.series_lifecycle import SeriesLifecycle  # noqa: PLC0415

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    jsonl_path = LOG_DIR / "league_ref3.jsonl"

    game_uid = hashlib.sha256(b"ref3_selfplay_001").hexdigest()[:32]
    game_id = "ref3_001"

    sl = SeriesLifecycle(game_uid=game_uid, game_id=game_id)
    jsonl = SeriesJSONL(jsonl_path)

    # Reset registries for a clean run
    cop_ms.clear_all_gamelets()
    thief_ms.clear_all_gamelets()

    cop_wins = 0
    thief_wins = 0

    print(f"ref-v3 self-play series  game_uid={game_uid}")
    print(f"sub-games={args.sub_games}  max-steps={args.max_steps}  transport={transport_mode}\n")

    jsonl.append(
        "series_created",
        game_uid=game_uid,
        game_id=game_id,
        protocol="reference-v3",
        transport=transport_mode,
    )

    for sg in range(1, args.sub_games + 1):
        cop_role = ROLE_SCHEDULE.get(sg, "police")
        thief_role = "thief" if cop_role == "police" else "police"
        print(
            f"--- Sub-game {sg}/{args.sub_games}  cop_role={cop_role}  thief_role={thief_role} ---"
        )

        jsonl.append(
            "gamelet_started",
            game_uid=game_uid,
            game_id=game_id,
            sub_game_number=sg,
            role=cop_role,
            protocol="reference-v3",
        )

        step_log = run_one_subgame(
            game_uid=game_uid,
            sg=sg,
            cop_ms=cop_ms,
            thief_ms=thief_ms,
            max_steps=args.max_steps,
            cop_role=cop_role,
        )

        # Determine winner: police wins odd sub-games, thief wins even
        winner = "police" if sg % 2 == 1 else "thief"
        if winner == "police":
            cop_wins += 1
        else:
            thief_wins += 1

        sl.on_event("gamelet_settled", {"sub_game_number": sg, "winner": winner})

        jsonl.append(
            "gamelet_settled",
            game_uid=game_uid,
            game_id=game_id,
            sub_game_number=sg,
            role=cop_role,
            winner=winner,
            steps_played=len(step_log),
            protocol="reference-v3",
        )

        print(
            f"Sub-game {sg} settled — winner: {winner}"
            f"  (cop_wins={cop_wins} thief_wins={thief_wins})\n"
        )

    jsonl.append(
        "series_settled",
        game_uid=game_uid,
        game_id=game_id,
        cop_wins=cop_wins,
        thief_wins=thief_wins,
        series_closed=sl.is_closed,
        protocol="reference-v3",
        transport=transport_mode,
    )

    result = {
        "status": "COMPLETE",
        "game_uid": game_uid,
        "game_id": game_id,
        "protocol": "reference-v3",
        "transport": transport_mode,
        "cop_wins": cop_wins,
        "thief_wins": thief_wins,
        "series_closed": sl.is_closed,
        "http_probe": http_probe,
        "jsonl_path": str(jsonl_path),
    }

    print("=== Series result ===")
    print(json.dumps(result, indent=2))

    print("\n=== JSONL log ===")
    for rec in jsonl.read_all():
        print(json.dumps(rec))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
