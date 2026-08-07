"""Generate and validate lifecycle artifact filenames and schemas.

Artifact naming convention:
  declaration_<game_uid>.json
  config_<game_uid>_g<NN>.json
  log_<game_uid>_g<NN>.json
  result_<game_uid>.json
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class LifecycleArtifactSet:
    """Links all four artifact types for one game series."""

    game_uid: str
    declaration_path: str  # declaration_<game_uid>.json
    config_paths: list[str]  # config_<game_uid>_g<NN>.json per gamelet
    log_paths: list[str]  # log_<game_uid>_g<NN>.json per gamelet
    result_path: str  # result_<game_uid>.json

    def validate_all_present(self) -> list[str]:
        """Return a list of paths that do not exist on disk."""
        all_paths = (
            [self.declaration_path] + self.config_paths + self.log_paths + [self.result_path]
        )
        return [p for p in all_paths if not Path(p).exists()]


def declaration_path(base_dir: str, game_uid: str) -> str:
    """Return the canonical path for a declaration artifact."""
    return str(Path(base_dir) / f"declaration_{game_uid}.json")


def config_path(base_dir: str, game_uid: str, gamelet: int) -> str:
    """Return the canonical path for a per-gamelet config artifact."""
    return str(Path(base_dir) / f"config_{game_uid}_g{gamelet:02d}.json")


def log_path(base_dir: str, game_uid: str, gamelet: int) -> str:
    """Return the canonical path for a per-gamelet log artifact."""
    return str(Path(base_dir) / f"log_{game_uid}_g{gamelet:02d}.json")


def result_path(base_dir: str, game_uid: str) -> str:
    """Return the canonical path for a result artifact."""
    return str(Path(base_dir) / f"result_{game_uid}.json")


def build_artifact_set(base_dir: str, game_uid: str, num_gamelets: int = 6) -> LifecycleArtifactSet:
    """Build a LifecycleArtifactSet for *num_gamelets* gamelets."""
    return LifecycleArtifactSet(
        game_uid=game_uid,
        declaration_path=declaration_path(base_dir, game_uid),
        config_paths=[config_path(base_dir, game_uid, g) for g in range(1, num_gamelets + 1)],
        log_paths=[log_path(base_dir, game_uid, g) for g in range(1, num_gamelets + 1)],
        result_path=result_path(base_dir, game_uid),
    )
