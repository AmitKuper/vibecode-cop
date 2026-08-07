"""PeerRuntime I/O helpers — persistence and config loading."""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from agent.reliability.durable_io import atomic_write_json

logger = logging.getLogger(__name__)


def _load_start_positions() -> tuple[list[int], list[int]]:
    """Load cop_start and thief_start from shared config."""
    try:
        from agent.config.shared_config import load_shared_config

        cfg = load_shared_config()
        ba = cfg.get("board_and_agents", {})
        return ba.get("cop_start", [0, 0]), ba.get("thief_start", [3, 3])
    except Exception:
        return [0, 0], [3, 3]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _git_commit() -> str:
    """Resolve the current HEAD commit SHA for provenance tracking."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def save_game_state(game_dir: Path, state: dict) -> None:
    atomic_write_json(game_dir / "game_state.json", state)


def store_commit(game_dir: Path, role: str, step: int, payload: dict) -> None:
    """Persist one commitment payload to disk."""
    path = game_dir / f"my_commitments_{role}.json"
    existing: dict = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            existing = json.load(f)
    existing[str(step)] = payload
    atomic_write_json(path, existing)


_GITHUB_REPOS_FALLBACK = {
    "cop": "https://github.com/amitKuper/vibecode-cop",
    "thief": "https://github.com/amitKuper/vibecode-thief",
}


def _load_github_repos() -> dict[str, str]:
    """Load GitHub repository URLs from shared config, with hardcoded fallback."""
    try:
        from agent.config.shared_config import load_shared_config
        cfg = load_shared_config()
        repos = cfg.get("github_repos", {})
        if repos:
            return repos
    except Exception:
        pass
    return _GITHUB_REPOS_FALLBACK


def _load_diversity_reward() -> int:
    try:
        from agent.config.shared_config import load_shared_config
        cfg = load_shared_config()
        return cfg.get("network_and_league", {}).get("diversity_reward", 10)
    except Exception:
        return 10


def write_result(
    game_dir: Path,
    game_id: str,
    role: str,
    config_sha256: str,
    group_name: str,
    board,
    state: dict,
    final_step: int,
    audit_ok: bool,
    my_commits: dict,
    opponent_commits_count: int,
    my_endpoint: str = "",
    opponent_group_id: str = "",
    token_counts: dict | None = None,
) -> None:
    """Write the agent-local result file for this game."""
    github_repos = _load_github_repos()
    result = {
        # Spec §9.3.3: team identity, game_uid, timestamps
        "game_id": game_id,
        "game_uid": game_id,
        "role": role,
        "group_name": group_name,
        "git_commit": _git_commit(),
        # Spec §9.3.3: GitHub URLs
        "github_repos": github_repos,
        # Spec §9.3.3: FastMCP server addresses
        "mcp_servers": {
            role: my_endpoint or "",
        },
        # Spec §9.3.3: groups (our side; opponent filled if known)
        "groups": {
            "us": {
                "group_name": group_name,
                "role": role,
                "github_repos": github_repos,
                "mcp_server": my_endpoint or "",
            },
            "opponent": {
                "group_id": opponent_group_id or "unknown",
            },
        },
        # Match result
        "config_sha256": config_sha256,
        "winner": state.get("winner"),
        "final_step": final_step,
        "abort_reason": state.get("abort_reason"),
        "audit_ok": audit_ok,
        "cop_final_position": board.cop_position,
        "thief_final_position": board.thief_position,
        "created_at": state.get("created_at"),
        "ended_at": state.get("ended_at"),
        "my_commits_count": len(my_commits),
        "opponent_commits_count": opponent_commits_count,
        # Spec §9.3.3: scoring fields
        "cop_score": state.get("cop_score"),
        "thief_score": state.get("thief_score"),
        "diversity_reward": _load_diversity_reward(),
        "first_meeting_between_groups": True,
        "games_played_including_this": 1,
        # Spec rule 54: token consumption
        "token_counts": token_counts or {"total": 0, "hint_generation": 0},
    }
    path = game_dir / f"result_{game_id}.json"
    atomic_write_json(path, result)
    logger.info(f"[PeerRuntime/{role}] Result written: {path}")
