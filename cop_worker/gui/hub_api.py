"""Hub API router: game history, live status, and the read-only settings view."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

RESULTS = Path(__file__).resolve().parents[2] / "results"
CONFIG = Path(__file__).resolve().parents[2] / "config"
LIVE_PORTS = {"cop": 8781, "thief": 8782}
OUR_GROUP = "vibecode"
#: Opponents that are local benches, not real teams (peer simulator, kit sparring).
SIM_GROUPS = {"peersim01", "sparring-match", "selftest"}

router = APIRouter()


def _counted_index() -> dict:
    """game_id -> ledger entry, from results/counted_series.json ({} if absent)."""
    try:
        ledger = json.loads((RESULTS / "counted_series.json").read_text(encoding="utf-8"))
        return {e.get("game_id"): e for e in ledger.get("series", [])}
    except (OSError, json.JSONDecodeError):
        return {}


def _stamp(started: str) -> str:
    """The per-run archive stamp artifacts_io derives from the first window."""
    return started[:19].replace(":", "").replace("-", "").replace("T", "-") or "unknown"


@router.get("/api/hub/games")
async def games() -> JSONResponse:
    """Every series with a result artifact, newest first, categorized.

    counted  - filed in the league ledger (results/counted_series.json)
    local    - a bench opponent (peer simulator / kit sparring), not a real team
    friendly - everything else. NOTE: result artifacts are per game_id, so only
    the LATEST series against an opponent is listed here; earlier friendlies
    against the same opponent live in reports/ref3_matches/ match logs.
    """
    counted = _counted_index()
    out = []
    seen_runs: set = set()  # (game_id, first-window started_at) - dedupe vs archive
    current = sorted(RESULTS.glob("result_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    archive = sorted((RESULTS / "history").glob("result_*.json"), reverse=True)
    for res in current + archive:
        try:
            doc = json.loads(res.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        game_id = doc.get("game_id", res.stem.removeprefix("result_"))
        started = ((doc.get("sub_games") or [{}])[0].get("started_at") or "")[:19]
        if (game_id, started) in seen_runs:
            continue  # the archive copy of a run already listed from results/
        seen_runs.add((game_id, started))
        from_archive = res.parent.name == "history"
        groups = doc.get("groups") or []
        opponent = next((g for g in groups if g != OUR_GROUP), "?")
        if game_id in counted and not from_archive:
            category = "counted"
        elif opponent in SIM_GROUPS:
            category = "local"
        else:
            # Archived runs are earlier series (friendlies) even when the SAME
            # game_id later counted - only the current ledger row is counted.
            category = "friendly"
        fr = doc.get("final_result", {})
        score = fr.get("total_score", {})
        out.append(
            {
                "game_id": game_id,
                "category": category,
                "group": OUR_GROUP,
                "opponent": opponent,
                "windows": len(doc.get("sub_games", [])),
                "score": " – ".join(f"{k} {v}" for k, v in score.items()),
                "winner": fr.get("winner_group"),
                "mutual_sha": (doc.get("mutual_agreement") or {}).get("sha256", ""),
                "confirmed": bool((doc.get("mutual_agreement") or {}).get("confirmed")),
                "report_id": ""
                if from_archive
                else (counted.get(game_id) or {}).get("report_message_id", ""),
                "started": started,
                # Gamelet logs rotate per game_id, so archived rows can't link
                # them - but per-run GAME RECORDS are archived under history/
                # (same stamp as the result), so those replay links survive.
                # Replay links prefer the game RECORDS (both sides, scent bytes,
                # barriers rendered); the sealed logs are the fallback when no
                # record exists (pre-2026-08-17 series).
                "logs": sorted(
                    f"history/{p.name}"
                    for p in (RESULTS / "history").glob(
                        f"record_{game_id}_g*_{_stamp(started)}.json"
                    )
                )
                if from_archive
                else (
                    sorted(p.name for p in RESULTS.glob(f"record_{game_id}_g*.json"))
                    or sorted(p.name for p in RESULTS.glob(f"log_{game_id}_g*.json"))
                ),
            }
        )
    # Human-vs-model games: persisted as replayable game records by play_record
    for rec in sorted(RESULTS.glob("record_human-vs-model_*.json"), reverse=True):
        try:
            doc = json.loads(rec.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stamp = str(doc.get("started_at") or "")
        started = (
            f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}"
            if len(stamp) >= 15
            else stamp
        )
        human_won = (doc.get("outcome") == "capture") == (doc.get("human_role") == "cop")
        out.append(
            {
                "game_id": "human-vs-model",
                "category": "human",
                "group": OUR_GROUP,
                "opponent": f"human ({doc.get('human_role')})",
                "windows": 1,
                "score": doc.get("outcome") or "?",
                "winner": "human" if human_won else "model",
                "mutual_sha": "",
                "confirmed": False,
                "report_id": "",
                "started": started,
                "logs": [rec.name],
            }
        )
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
