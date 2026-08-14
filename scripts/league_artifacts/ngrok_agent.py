"""Start (or reuse) the local ngrok agent that fronts our MCP doors.

Idempotent by design: if the agent is already serving the tunnel we want, this
does nothing. A match must never fail because of ingress, so every failure path
returns quietly and lets `resolve_mcp_urls` fall back to the static IP.

Free-tier reality: the account has ONE static domain, and ngrok injects it into
every tunnel that does not name its own URL. Starting two tunnels therefore
makes both advertise the same hostname while only the last registration routes.
So we start exactly ONE named tunnel (the cop door by default); the thief door
keeps declaring the router-forwarded IP.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from league_artifacts.ingress import LOCAL_PORTS, _tunnel_map

#: Tunnel definitions live outside both repos (no secrets; the authtoken stays
#: in ngrok's own default config).
TUNNELS_YML = Path(__file__).resolve().parents[3] / "tools" / "ngrok_tunnels.yml"
DEFAULT_TUNNEL = "cop"


def _default_config() -> Path | None:
    """ngrok's own config (holds the authtoken). None if it isn't there.

    A Microsoft Store (MSIX) install redirects %LOCALAPPDATA% into the package's
    LocalCache, so the plain path is empty even though `ngrok config check`
    reports one. Passing --config for our tunnels REPLACES the default set, so
    missing this file means an agent with no authtoken, which silently never
    comes up (observed 2026-08-14).
    """
    import os

    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".config")
    candidates = [
        base / "ngrok" / "ngrok.yml",
        Path.home() / ".ngrok2" / "ngrok.yml",
        *sorted((base / "Packages").glob("*ngrok*/LocalCache/Local/ngrok/ngrok.yml")),
    ]
    return next((c for c in candidates if c.is_file()), None)


def agent_command(tunnel: str = DEFAULT_TUNNEL) -> list[str] | None:
    """The exact command we would run, or None if ngrok/config is unavailable."""
    exe = shutil.which("ngrok")
    if not exe or not TUNNELS_YML.is_file():
        return None
    cmd = [exe, "start", tunnel]
    cfg = _default_config()
    if cfg:
        cmd += ["--config", str(cfg)]
    cmd += ["--config", str(TUNNELS_YML)]
    return cmd


def ensure_tunnel(
    tunnel: str = DEFAULT_TUNNEL, *, wait_s: float = 15.0, announce=print
) -> str | None:
    """Return the public URL for `tunnel`'s port, starting the agent if needed."""
    role_port = LOCAL_PORTS.get(tunnel)
    live = _tunnel_map().get(role_port) if role_port else None
    if live:
        return live  # already up: reuse, never restart mid-session
    cmd = agent_command(tunnel)
    if cmd is None:
        if announce:
            announce("[ingress] ngrok not installed or tools/ngrok_tunnels.yml missing")
        return None
    try:
        subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        if announce:
            announce(f"[ingress] could not start ngrok ({type(exc).__name__}) - staying static")
        return None
    deadline = time.time() + wait_s
    while time.time() < deadline:
        live = _tunnel_map().get(role_port) if role_port else None
        if live:
            if announce:
                announce(f"[ingress] started ngrok tunnel '{tunnel}': {live}")
            return live
        time.sleep(0.5)
    if announce:
        announce(f"[ingress] ngrok did not report tunnel '{tunnel}' within {wait_s:.0f}s")
    return None
