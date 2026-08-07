"""Series-level declaration — creates declaration_{game_id}.json at league start."""

from __future__ import annotations

import json
import logging
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SeriesDeclaration:
    """Signed declaration for one series, created before play begins."""

    game_id: str
    game_uid: str
    group_id: str
    opponent_group: str
    role: str
    cpu_model: str
    cpu_frequency_ghz: float | None
    gpu_model: str
    git_sha: str
    git_clean: bool


def get_git_sha(repo_path: str | Path = ".") -> str:
    """Return the current HEAD git SHA for the repo.

    Args:
        repo_path: Path to the git repository root.

    Returns:
        40-char hex SHA string.

    Raises:
        RuntimeError: If git command fails.
    """
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git rev-parse failed: {result.stderr}")
    return result.stdout.strip()


def is_git_clean(repo_path: str | Path = ".") -> bool:
    """Return True if the working tree is clean (no uncommitted changes).

    Args:
        repo_path: Path to the git repository root.

    Returns:
        True if no uncommitted changes exist.
    """
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode == 0 and result.stdout.strip() == ""


def get_hardware_info() -> dict:
    """Return basic hardware info for the declaration.

    Returns:
        Dict with cpu_model, cpu_frequency_ghz, and gpu_model keys.
    """
    info: dict = {
        "cpu_model": platform.processor() or "unknown",
        "cpu_frequency_ghz": None,
        "gpu_model": "unknown",
    }
    try:
        import psutil

        freq = psutil.cpu_freq()
        if freq:
            info["cpu_frequency_ghz"] = round(freq.max / 1000, 2)
    except ImportError:
        pass
    return info


def write_series_declaration(
    game_id: str,
    game_uid: str,
    group_id: str,
    opponent_group: str,
    role: str,
    output_dir: str | Path = ".",
    counted: bool = False,
    repo_path: str | Path = ".",
) -> Path:
    """Write declaration_{game_id}.json for a series.

    Args:
        game_id: Protocol/course game identifier.
        game_uid: Canonical cryptographic series identity.
        group_id: Our group identifier.
        opponent_group: Opponent's group identifier.
        role: Our starting role ('police' or 'thief').
        output_dir: Directory to write the declaration.
        counted: If True, fail hard on dirty git state.
        repo_path: Path to the git repo for SHA + clean check.

    Returns:
        Path to the written declaration file.

    Raises:
        RuntimeError: If counted=True and repo is dirty.
    """
    hw = get_hardware_info()
    git_sha = get_git_sha(repo_path)
    git_clean = is_git_clean(repo_path)
    if counted and not git_clean:
        raise RuntimeError("Counted match requires clean git state")
    decl = SeriesDeclaration(
        game_id=game_id,
        game_uid=game_uid,
        group_id=group_id,
        opponent_group=opponent_group,
        role=role,
        cpu_model=hw["cpu_model"],
        cpu_frequency_ghz=hw["cpu_frequency_ghz"],
        gpu_model=hw["gpu_model"],
        git_sha=git_sha,
        git_clean=git_clean,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"declaration_{game_id}.json"
    path.write_text(json.dumps(decl.__dict__, indent=2))
    logger.info("Wrote series declaration: %s", path)
    return path
