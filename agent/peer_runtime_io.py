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
) -> None:
    """Write the agent-local result file for this game."""
    result = {
        "game_id": game_id,
        "role": role,
        "config_sha256": config_sha256,
        "group_name": group_name,
        "git_commit": _git_commit(),
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
    }
    path = game_dir / f"result_{game_id}.json"
    atomic_write_json(path, result)
    logger.info(f"[PeerRuntime/{role}] Result written: {path}")
