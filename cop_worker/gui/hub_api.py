"""Hub API router: game history, live status, and the read-only settings view.

Row assembly for the games endpoint lives in hub_games.py (150-line rule).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from cop_worker.gui.hub_games import _counted_index, human_rows, series_rows

CONFIG = Path(__file__).resolve().parents[2] / "config"
LIVE_PORTS = {"cop": 8781, "thief": 8782}

router = APIRouter()


@router.get("/api/hub/games")
async def games() -> JSONResponse:
    """Every series with a result artifact, newest first, categorized.

    counted  - filed in the league ledger (results/counted_series.json)
    local    - a bench opponent (peer simulator / kit sparring), not a real team
    friendly - everything else. NOTE: result artifacts are per game_id, so only
    the LATEST series against an opponent is listed here; earlier friendlies
    against the same opponent live in reports/ref3_matches/ match logs.
    """
    out = series_rows(_counted_index()) + human_rows()
    # newest first regardless of source: current results/ and the recovered
    # archive interleave (recovered runs otherwise cluster at the tail)
    out.sort(key=lambda r: r["started"], reverse=True)
    return JSONResponse(out)


@router.get("/api/hub/live")
async def live_status() -> JSONResponse:
    """Probe the per-role live GUIs (up only while a match is running)."""
    import httpx

    out = {}
    for role, port in LIVE_PORTS.items():
        state: dict = {"up": False}
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                resp = await client.get(f"http://127.0.0.1:{port}/api/view")
            if resp.status_code == 200:
                view = resp.json().get("view", {})
                state = {
                    "up": True,
                    "sub_game": view.get("sub_game"),
                    "step": view.get("turn"),
                    "your_turn": view.get("your_turn"),
                }
        except Exception:
            pass  # not running - the normal idle state, never an error
        out[role] = state
    return JSONResponse(out)


@router.get("/api/hub/settings")
async def settings() -> JSONResponse:
    """Read-only view of the operative runtime config - the dashboard NEVER writes."""
    import tomllib

    base = tomllib.loads((CONFIG / "runtime.toml").read_text(encoding="utf-8"))
    net, proto = base.get("network", {}), base.get("protocol", {})
    rep = base.get("report", {})
    return JSONResponse(
        {
            "ingress": net.get("ingress", "static"),
            "our_cop_port": net.get("our_cop_port"),
            "our_thief_port": net.get("our_thief_port"),
            "gui_cop_port": net.get("gui_cop_port"),
            "gui_thief_port": net.get("gui_thief_port"),
            "scent_model": proto.get("scent_model"),
            "move_policy": proto.get("move_policy"),
            "report_recipient": rep.get("recipient"),
            "report_mode": rep.get("mode"),
            # live truth from the ledger - the base-config value is a per-profile
            # default and was showing a stale "1" while six series were filed
            "counted_played": len(_counted_index()),
            "profiles": sorted(p.name for p in (CONFIG / "opponents").glob("*") if p.is_dir()),
        }
    )
