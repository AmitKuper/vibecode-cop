"""Row builders for the hub games endpoint (split from hub_api, 150-line rule)."""

from __future__ import annotations

import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[2] / "results"
OUR_GROUP = "vibecode"
#: Opponents that are local benches, not real teams (peer simulator, kit sparring).
SIM_GROUPS = {"peersim01", "sparring-match", "selftest"}


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


def _replay_logs(game_id: str, started: str, from_archive: bool) -> list[str]:
    # Gamelet logs rotate per game_id, so archived rows can't link them - but
    # per-run GAME RECORDS are archived under history/ (same stamp as the
    # result), so those replay links survive. Replay links prefer the game
    # RECORDS (both sides, scent bytes, barriers rendered); the sealed logs are
    # the fallback when no record exists (pre-2026-08-17 series).
    if from_archive:
        return sorted(
            f"history/{p.name}"
            for p in (RESULTS / "history").glob(f"record_{game_id}_g*_{_stamp(started)}.json")
        )
    return sorted(p.name for p in RESULTS.glob(f"record_{game_id}_g*.json")) or sorted(
        p.name for p in RESULTS.glob(f"log_{game_id}_g*.json")
    )


def series_rows(counted: dict) -> list[dict]:
    """Every series with a result artifact, categorized (counted/local/friendly)."""
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
                "logs": _replay_logs(game_id, started, from_archive),
            }
        )
    return out


def human_rows() -> list[dict]:
    """Human-vs-model games: persisted as replayable game records by play_record."""
    out = []
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
    return out
