"""Pre-game declaration artifact: identities, hardware, MCP endpoints, signatures."""

from __future__ import annotations

from league_artifacts.core import OUR_REPOS, _sha, our_mcp


def _hardware_spec() -> dict:
    try:
        import platform

        import psutil

        return {
            "cpu_cores": psutil.cpu_count(logical=True),
            "cpu_type": platform.processor() or "unknown",
            "os": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "ram_gb": round(psutil.virtual_memory().total / 1e9),
        }
    except Exception:
        return {}


def build_declaration(
    game_id: str,
    game_uid: str,
    opponent: str,
    members: list,
    cop_commit: str,
    started_at: str,
    ended_at: str,
    opp_identity: dict | None = None,
    our_counted: int = 0,
    thief_commit: str | None = None,
) -> dict:
    hw = _hardware_spec()
    # No github_commit in the declaration: the reference keeps per-sub-game commit in the
    # log step_zero and result rows (that's where both stacks already put it). cop_commit /
    # thief_commit params are retained for caller compatibility but no longer emitted here.
    ours = {
        "code_version": "1.00",
        "counted_games_played": our_counted,
        "group_id": "vibecode",
        "group_name": "vibecode",
        "hardware_spec": hw,
        "hardware_spec_sha256": _sha(hw) if hw else "",
        "llm_model": "none (template hints; pure-Python algorithmic movement)",
        "mcp_servers": our_mcp(),
        "members": members,
        "repos": OUR_REPOS,
        "signature": f"sha256:{_sha({'group_id': 'vibecode', 'game_uid': game_uid})}",
    }
    oi = opp_identity or {}
    theirs = {
        "group_id": oi.get("group_id", opponent),
        "group_name": oi.get("group_name", opponent),
        "counted_games_played": oi.get("counted_games_played", 0),
        "hardware_spec": oi.get("hardware_spec", {}),
        "hardware_spec_sha256": "",
        "llm_model": oi.get("llm_model", "unknown"),
        "mcp_servers": oi.get("mcp_servers", {}),
        "members": oi.get("members", []),
        "repos": oi.get("repos", {}),
        "signature": oi.get("signature", "undeclared"),
    }
    return {
        "_schema": "p2p-police-artifacts",
        "consensus_signature": _sha({"uid": game_uid, "g": sorted(["vibecode", opponent])}),
        "declaration_type": "pre_game_declaration",
        "declared_at": ended_at,
        "game_ended_at": ended_at,
        "game_id": game_id,
        "game_started_at": started_at,
        "game_uid": game_uid,
        "groups": {"group_1": ours, "group_2": theirs},
        "links": {
            "config": f"config_{game_id}_g<NN>.json",
            "declaration": f"declaration_{game_id}.json",
            "log": f"log_{game_id}_g<NN>.json",
            "result": f"result_{game_id}.json",
        },
        "max_tokens_per_game": 200000,
        "num_sub_games": 6,
        "report_type": "declaration",
        "schema_version": "1.00",
        "timezone": "Asia/Jerusalem",
        "token_budget_per_series": 200000,
    }
