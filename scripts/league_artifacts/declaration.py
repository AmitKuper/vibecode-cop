"""Pre-game declaration artifact: identities, hardware, MCP endpoints, signatures."""

from __future__ import annotations

from league_artifacts.core import OUR_REPOS, _sha, our_mcp


def _ram_gb() -> int | None:
    """Total RAM without psutil (it is not in the runtime venv — an ImportError here
    used to blank the whole spec, which najamjad flagged 2026-08-14)."""
    try:
        import ctypes
        import os

        if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names:
            return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9)

        class _MemStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        st = _MemStatus()
        st.dwLength = ctypes.sizeof(_MemStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        return round(st.ullTotalPhys / 1e9)
    except Exception:
        return None


def _hardware_spec() -> dict:
    """Stdlib-only system spec (rule: Step-0 must carry one; never emit an empty dict)."""
    import os
    import platform

    spec = {
        "cpu_cores": os.cpu_count(),
        "cpu_type": platform.processor() or platform.machine() or "unknown",
        "machine": platform.machine(),
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
    }
    ram = _ram_gb()
    if ram:
        spec["ram_gb"] = ram
    return spec


def counted_opponents() -> list:
    """Group ids of our already-counted series, from the league ledger (rule 38:
    the two teams' declarations are judged for consistency, so this must be live)."""
    import json
    from pathlib import Path

    ledger = Path(__file__).resolve().parents[2] / "results" / "counted_series.json"
    try:
        rows = json.loads(ledger.read_text(encoding="utf-8")).get("series", [])
        return sorted({r["opponent"] for r in rows if r.get("opponent")})
    except Exception:
        return []


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
        # Same integer under both spellings peers use (najamjad 2026-08-14): a reader
        # keying on either name gets the same number and they cannot disagree.
        "counted_matches_played": our_counted,
        "opponents_already_counted": counted_opponents(),
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
