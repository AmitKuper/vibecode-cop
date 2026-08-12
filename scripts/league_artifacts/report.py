"""Counted-ledger filing and the result email (body + attachment, same bytes)."""

from __future__ import annotations

import json
from pathlib import Path

from league_artifacts.core import now_iso


def update_counted_ledger(
    ledger_path: Path,
    *,
    game_id: str,
    game_uid: str,
    opponent: str,
    result_obj: dict,
    message_id: str | None,
    our_counted_before: int,
) -> dict:
    """Record this counted series in results/counted_series.json (the league ledger).

    Idempotent by game_id (rule 52: only one counted match per rival, so re-filing the same
    series overwrites rather than duplicates). counted_games_played tracks the number of
    distinct counted series filed = our declared count once this one lands.
    """
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    else:
        ledger = {"group_id": "vibecode", "counted_games_played": our_counted_before, "series": []}
    fr = result_obj["final_result"]
    entry = {
        "game_id": game_id,
        "game_uid": game_uid,
        "opponent": opponent,
        "winner_group": fr["winner_group"],
        "total_score": fr["total_score"],
        "sub_games_won": fr["sub_games_won"],
        "diversity_reward_applied": fr["diversity_reward_applied"],
        "mutual_agreement": result_obj["mutual_agreement"],
        "report_message_id": message_id,
        "reported_at": now_iso(),
        "result_file": f"result_{game_id}.json",
    }
    series = [s for s in ledger.get("series", []) if s.get("game_id") != game_id]
    series.append(entry)
    ledger["series"] = series
    ledger["counted_games_played"] = len(series)
    ledger["updated_at"] = now_iso()
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")
    return ledger


def email_result(result: dict, recipient: str, filename: str, token_path: Path) -> str:
    """Email the result: pretty-printed body + one attachment (same bytes), like anrbj666's.

    Subject: 'P2P league SERIES result - <game_id> - winner=<w> - <a>:<sa> <b>:<sb>'.
    """
    from email.mime.application import MIMEApplication
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    from league_manager.reports.gmail_send import gmail_api_send, load_oauth_credentials

    body = json.dumps(result, indent=2, ensure_ascii=False)
    fr = result["final_result"]
    ts = fr["total_score"]
    score_str = " ".join(f"{g}:{ts[g]}" for g in result["groups"])
    subject = (
        f"P2P league SERIES result - {result['game_id']} - "
        f"winner={fr['winner_group']} - {score_str}"
    )
    msg = MIMEMultipart()
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    att = MIMEApplication(body.encode("utf-8"), _subtype="json")
    att.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(att)
    return gmail_api_send(msg, load_oauth_credentials(token_path))
