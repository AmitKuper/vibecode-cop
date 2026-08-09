"""Central config loader — one place to find every main parameter for a game.

Two config kinds live under ``config/`` (see ``config/README.md``):

* ``game.json``    — the shared constitution. Its whole-file canonical SHA is
  ``config_sha256`` (exchanged with the opponent). Single source of truth for
  every GAME parameter (board, scent, scoring, movement).
* ``runtime.toml`` — private runtime params (network, timeouts, llm, identity,
  report). Never hashed, never shared.

Profile selection (``--config``):
    load_config(None)          -> base profile: config/game.json + config/runtime.toml
    load_config("anrbj666")    -> config/opponents/anrbj666/ if present, else base
    load_config("/abs/dir")    -> that directory
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:  # py311+ stdlib
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

# repo root = parent of cop_worker/
REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "config"


class ConfigError(RuntimeError):
    """Raised when a requested config profile cannot be resolved or parsed."""


def resolve_profile_dir(name_or_path: str | None) -> Path:
    """Return the directory a ``--config`` value resolves to (does not read files)."""
    if not name_or_path:
        return CONFIG_DIR
    p = Path(name_or_path)
    if p.is_dir():  # explicit directory path
        return p
    opp = CONFIG_DIR / "opponents" / name_or_path
    if opp.is_dir():
        return opp
    # A bare name with no saved profile falls back to the base config dir.
    return CONFIG_DIR


def _load_game(profile_dir: Path) -> dict[str, Any]:
    # game.json always resolves to a real constitution: prefer the profile's
    # copy, fall back to the base so a thin opponent profile need only override
    # runtime.toml.
    for candidate in (profile_dir / "game.json", CONFIG_DIR / "game.json"):
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise ConfigError(f"no game.json found for profile {profile_dir}")


def _load_runtime(profile_dir: Path) -> dict[str, Any]:
    for candidate in (profile_dir / "runtime.toml", CONFIG_DIR / "runtime.toml"):
        if candidate.is_file():
            return tomllib.loads(candidate.read_text(encoding="utf-8"))
    raise ConfigError(f"no runtime.toml found for profile {profile_dir}")


def load_config(name_or_path: str | None = None) -> dict[str, Any]:
    """Return ``{"game": <dict>, "runtime": <dict>, "profile_dir": Path, "source": str}``."""
    profile_dir = resolve_profile_dir(name_or_path)
    return {
        "game": _load_game(profile_dir),
        "runtime": _load_runtime(profile_dir),
        "profile_dir": profile_dir,
        "source": name_or_path or "config (base)",
    }


def load_game(name_or_path: str | None = None) -> dict[str, Any]:
    """Just the shared constitution (game.json) for the resolved profile."""
    return _load_game(resolve_profile_dir(name_or_path))


def load_runtime(name_or_path: str | None = None) -> dict[str, Any]:
    """Just the runtime params (runtime.toml) for the resolved profile."""
    return _load_runtime(resolve_profile_dir(name_or_path))
