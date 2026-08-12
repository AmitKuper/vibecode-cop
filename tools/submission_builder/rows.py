"""Ledger-derived game rows, totals, and placeholder scanning.

Game rows and totals are DERIVED (never typed by hand) from the league ledger
``results/counted_series.json`` plus the per-game ``result_*.json`` artifacts.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.pdf_parser.reader import PdfParserError

IL = timezone(timedelta(hours=3))  # Asia/Jerusalem league clock


def load_games(results_dir: str | Path, group_id: str = "vibecode") -> list[dict]:
    """One row per ledger entry, times converted to the league clock."""
    results_dir = Path(results_dir)
    ledger_path = results_dir / "counted_series.json"
    if not ledger_path.is_file():
        raise PdfParserError(f"no league ledger at {ledger_path}")
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    games = []
    for entry in ledger["series"]:
        result = json.loads(
            (results_dir / f"result_{entry['game_id']}.json").read_text(encoding="utf-8")
        )
        sub = result["sub_games"]
        start = datetime.fromisoformat(sub[0]["started_at"]).astimezone(IL)
        end = datetime.fromisoformat(sub[-1]["ended_at"]).astimezone(IL)
        opponent = entry["opponent"]
        declared = result["final_result"].get("games_played_including_this", {})
        games.append(
            {
                "date": start.strftime("%Y-%m-%d"),
                "start": start.strftime("%H:%M"),
                "end": end.strftime("%H:%M"),
                "opponent": opponent,
                "us": entry["total_score"][group_id],
                "them": entry["total_score"][opponent],
                "declared": declared.get(opponent, ""),
                "won": entry["winner_group"] == group_id,
                "tie": entry.get("series_tie", False),
            }
        )
    return games


def compute_totals(games: list[dict]) -> dict:
    return {
        "legal_games": len(games),
        "points": sum(g["us"] for g in games),
        "won": sum(g["won"] and not g["tie"] for g in games),
        "lost": sum((not g["won"]) and not g["tie"] for g in games),
        "drawn": sum(bool(g["tie"]) for g in games),
    }


def unfilled_placeholders(data: dict) -> list[str]:
    """Every non-comment value still carrying a <FILL...> marker."""
    found: list[str] = []

    def _scan(obj, path=""):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if not str(key).startswith("_"):
                    _scan(value, f"{path}.{key}" if path else str(key))
        elif isinstance(obj, str) and "<FILL" in obj:
            found.append(f"{path} = {obj}")

    _scan(data)
    return found
