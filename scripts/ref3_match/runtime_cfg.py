"""Shared paths, action deltas, and the applied runtime.toml (timeout source)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
KIT_ROOT = REPO_ROOT.parent / "external" / "copthief-league-protocol"

# Cop barrier placement: target cell = own_position + delta (mirrors domain/transition.py).
_PLACE_DELTAS = {"PLACE_N": (0, -1), "PLACE_S": (0, 1), "PLACE_E": (1, 0), "PLACE_W": (-1, 0)}

# Runtime params (timeouts, reorder window, ...) sourced from config/runtime.toml at match
# start via apply_runtime_config(). Empty by default so the self-test / unit tests keep the
# original hardcoded fallbacks passed to _t().
_RT: dict = {}


def _t(key: str, default):
    """Read a [timeouts] value from the applied runtime config, else the hardcoded fallback."""
    return _RT.get("timeouts", {}).get(key, default)


def runtime_snapshot() -> dict:
    """The applied runtime config, for handing to a spawned role-worker process."""
    return dict(_RT)


def apply_runtime_config(runtime: dict) -> None:
    """Install a loaded runtime.toml (from config_loader) for the helpers below to read."""
    global _RT
    _RT = dict(runtime or {})


def _git_head(repo: Path) -> str:
    import subprocess

    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        return out or "unknown"
    except Exception:
        return "unknown"
