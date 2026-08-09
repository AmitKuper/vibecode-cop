#!/usr/bin/env python3
"""Build the four league artifact kinds (config, log, declaration, result).

Schemas mirror anrbj666's shipped files (ARTIFACT_FORMATS.md). All four are written
to the repo per game; ONLY the result (final_game_result) is emailed — body = its
canonical bytes, one attachment = the same bytes under result_<game_id>.json.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC
from pathlib import Path

from cop_worker.protocol.reference_v3 import canonical_json

REPO_ROOT = Path(__file__).resolve().parents[1]
OUR_REPOS = {"cop": "https://github.com/AmitKuper/vibecode-cop",
             "thief": "https://github.com/AmitKuper/vibecode-thief"}
OUR_MCP = {"cop": "http://62.56.220.143:61224/mcp", "thief": "http://62.56.220.143:61223/mcp"}

# The shared constitution (rule 11): both repos load byte-identical config/game.json.
# config_sha256 is sha256(canonical(WHOLE game.json)) — a field subset would defeat the
# purpose (two teams "agreeing" while unhashed sections differ). anrbj666 pins 9ed3b2e9….
GAME_JSON_PATH = REPO_ROOT / "config" / "game.json"


def _sha(obj: object) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def load_constitution() -> dict:
    """Load the shared game.json (lazy — a missing file must not crash on import)."""
    return json.loads(GAME_JSON_PATH.read_text(encoding="utf-8"))


def config_sha256() -> str:
    """sha256(canonical(whole game.json)) — must equal the peer's 9ed3b2e9…."""
    return _sha(load_constitution())


def now_iso() -> str:
    from datetime import datetime
    return datetime.now(UTC).isoformat()


def score_series(sub_games: list, opponent: str, game_id: str, *,
                 our_played: int = 0, opp_played: int = 0, counted: bool = False) -> tuple:
    """Return (rows, final_result) in the final_game_result schema.

    Appendix-F scoring: capture -> cop 20 / thief 5; survival -> thief 10 / cop 5.
    github_commit is per-sub-game (each side's repo HEAD for the role it played).
    games_played_including_this increments by 1 ONLY for a counted game (rules 37-38).
    """
    rows, tot_us, tot_them, won_us, won_them = [], 0, 0, 0, 0
    for sg in sub_games:
        n, role = sg["sub_game"], sg["role"]
        cop_s, thief_s = (20, 5) if sg.get("outcome") == "capture" else (5, 10)
        us, them = (cop_s, thief_s) if role == "police" else (thief_s, cop_s)
        tot_us += us
        tot_them += them
        won_us += us > them
        won_them += them > us
        opp_commit = (sg.get("opp_identity") or {}).get("github_commit", "unknown")
        rows.append({
            "sub_game_number": n,
            "roles": {"vibecode": role, opponent: "thief" if role == "police" else "police"},
            "started_at": sg.get("started_at", ""),
            "ended_at": sg.get("ended_at", ""),
            "result": sg.get("outcome"),
            "winner_group": "vibecode" if us > them else opponent,
            "tie": False,
            "github_commit": {"vibecode": sg.get("our_commit", "unknown"), opponent: opp_commit},
            "tokens": {"vibecode": 0, opponent: 0},
            "score": {"vibecode": us, opponent: them},
            "log_files": {"vibecode": f"log_{game_id}_g{n:02d}.json",
                          opponent: f"log_{game_id}_g{n:02d}.json"},
            "audit": {"log_verified": bool(sg.get("audit_ok")), "tampered": False},
        })
    inc = 1 if counted else 0
    # Tie rule: SERIES-LEVEL ADDITIVE (`series_add`) — on a level accumulated score each
    # team's total gains the App-F tie score (2). The book puts the award at the series
    # level (ch.9, App. F table 17 row 5); the reference sums per sub-game instead; course
    # staff ruled it a documented-choice contradiction. Every checked league team
    # (imreeyal, anrbj666, best2934) and the kit play series_add, and we DECLARE the rule
    # to the opponent before the first window (WARNINGS §6a) — a tie surfacing it
    # mid-series is the rule-35 two-reports shape.
    series_tie = tot_us == tot_them
    tie_score_each = int(load_constitution().get("scoring", {}).get("tie_score", 2))
    if series_tie:
        tot_us += tie_score_each
        tot_them += tie_score_each
    winner = ("vibecode" if tot_us > tot_them
              else opponent if tot_them > tot_us else None)
    # Diversity incentive (Appendix F, rule: "a win against a new opponent receives the full
    # diversity reward = 10"). Rule 52 allows only ONE counted match per rival, so a counted
    # series is by definition the first counted meeting with this opponent — a counted WIN is
    # always a win against a new counted opponent. Flag the winner; the +10 is a standings
    # bonus the league applies from this flag (per-series total_score is unchanged). Friendlies
    # (counted=False) and series ties (no winner) stay {False, False}.
    diversity = {"vibecode": False, opponent: False}
    if counted and winner is not None:
        diversity[winner] = True
    final_result = {
        "total_score": {"vibecode": tot_us, opponent: tot_them},
        "sub_games_won": {"vibecode": won_us, opponent: won_them},
        "ties": 0,
        "winner_group": winner,
        # tie_rule series_add is DECLARED in the written pairing agreement, never as an
        # extra result field — the grader's template is the authority (imreeyal §3.17).
        "series_tie": series_tie,
        "tokens_total_series": {"vibecode": 0, opponent: 0},
        "games_played_including_this": {"vibecode": our_played + inc, opponent: opp_played + inc},
        "first_meeting_between_groups": True,
        "diversity_reward_applied": diversity,
    }
    return rows, final_result


def build_config(game_id: str, game_uid: str, sub_game: int, setting: str, opponent: str) -> dict:
    """Config artifact sourced entirely from the shared constitution (config/game.json).

    Every section (including agreed_between and the whole-file config_sha256) comes from the
    adopted file so the artifact can never drift from the hashed bytes. `setting` is retained
    for signature compatibility but ignored — map_area lives in the constitution.
    """
    g = load_constitution()
    return {
        "_schema": "p2p-police-artifacts",
        "agreed_between": g["agreed_between"],
        "board_and_agents": g["board_and_agents"],
        "config_name": f"config_{game_id}_g{sub_game:02d}.json",
        "config_sha256": config_sha256(),
        "game_id": game_id, "game_uid": game_uid,
        "links": OUR_REPOS,
        "movement_and_barriers": g["movement_and_barriers"],
        "network_and_league": g["network_and_league"],
        "pheromones": g["pheromones"],
        "rate_limiter_gatekeeper": g["rate_limiter_gatekeeper"],
        "report_type": "config", "schema_version": g["schema_version"],
        "scoring": g["scoring"], "sub_game_number": sub_game, "world": g["world"],
    }


def build_log(game_id: str, game_uid: str, sub_game: int, role: str, opponent: str,
              our_records: list, opp_records: list, summary: dict) -> dict:
    """Log artifact. records[0] is the REAL sealed step_zero that rode the wire in
    submit_audit (fresh nonce, commit = reference_commit(payload, nonce)) — no longer
    synthesized here; it comes straight from out_session.local_records.
    """
    return {
        "_schema": "p2p-police-artifacts",
        "game_id": game_id, "game_uid": game_uid,
        "links": {"config": f"config_{game_id}_g{sub_game:02d}.json",
                  "declaration": f"declaration_{game_id}.json",
                  "log": f"log_{game_id}_g{sub_game:02d}.json",
                  "result": f"result_{game_id}.json"},
        "opponent_records": opp_records,
        "records": our_records,
        "report_type": "log", "schema_version": "1.3",
        "sub_game_number": sub_game, "summary": summary, "wire_shape": "reference",
    }


def _hardware_spec() -> dict:
    try:
        import platform

        import psutil
        return {"cpu_cores": psutil.cpu_count(logical=True),
                "cpu_type": platform.processor() or "unknown",
                "os": f"{platform.system()} {platform.release()}",
                "python": platform.python_version(),
                "ram_gb": round(psutil.virtual_memory().total / 1e9)}
    except Exception:
        return {}


def build_declaration(game_id: str, game_uid: str, opponent: str, members: list,
                      cop_commit: str, started_at: str, ended_at: str,
                      opp_identity: dict | None = None, our_counted: int = 0,
                      thief_commit: str | None = None) -> dict:
    hw = _hardware_spec()
    # No github_commit in the declaration: the reference keeps per-sub-game commit in the
    # log step_zero and result rows (that's where both stacks already put it). cop_commit /
    # thief_commit params are retained for caller compatibility but no longer emitted here.
    ours = {
        "code_version": "1.00", "counted_games_played": our_counted,
        "group_id": "vibecode", "group_name": "vibecode",
        "hardware_spec": hw, "hardware_spec_sha256": _sha(hw) if hw else "",
        "llm_model": "role-specific-recurrent-policy",
        "mcp_servers": OUR_MCP, "members": members, "repos": OUR_REPOS,
        "signature": f"sha256:{_sha({'group_id': 'vibecode', 'game_uid': game_uid})}",
    }
    oi = opp_identity or {}
    theirs = {
        "group_id": oi.get("group_id", opponent), "group_name": oi.get("group_name", opponent),
        "counted_games_played": oi.get("counted_games_played", 0),
        "hardware_spec": oi.get("hardware_spec", {}), "hardware_spec_sha256": "",
        "llm_model": oi.get("llm_model", "unknown"), "mcp_servers": oi.get("mcp_servers", {}),
        "members": oi.get("members", []), "repos": oi.get("repos", {}),
        "signature": oi.get("signature", "undeclared"),
    }
    return {
        "_schema": "p2p-police-artifacts",
        "consensus_signature": _sha({"uid": game_uid, "g": sorted(["vibecode", opponent])}),
        "declaration_type": "pre_game_declaration",
        "declared_at": ended_at, "game_ended_at": ended_at, "game_id": game_id,
        "game_started_at": started_at, "game_uid": game_uid,
        "groups": {"group_1": ours, "group_2": theirs},
        "links": {"config": f"config_{game_id}_g<NN>.json",
                  "declaration": f"declaration_{game_id}.json",
                  "log": f"log_{game_id}_g<NN>.json", "result": f"result_{game_id}.json"},
        "max_tokens_per_game": 200000, "num_sub_games": 6,
        "report_type": "declaration", "schema_version": "1.00",
        "timezone": "Asia/Jerusalem", "token_budget_per_series": 200000,
    }


def mutual_agreement_sha(game_id: str, rows: list, final_result: dict) -> str:
    """anrbj666/imreeyal ADR-0012 symmetric-outcome scope — the two-team standard.

    Preimage keyed on game_id; aggregate {series_tie, sub_games_won, ties, total_score,
    winner_group}; rows {sub_game_number, roles, result, winner_group, score}. Serialized
    in the SETTLEMENT form: sort_keys=True, ensure_ascii=False, DEFAULT (spaced) separators
    (NOT the compact commit canonical).
    """
    preimage = {
        "game_id": game_id,
        "aggregate": {
            "series_tie": final_result["series_tie"],
            "sub_games_won": final_result["sub_games_won"],
            "ties": final_result["ties"],
            "total_score": final_result["total_score"],
            "winner_group": final_result["winner_group"],
        },
        "sub_games": [{"sub_game_number": r["sub_game_number"], "roles": r["roles"],
                       "result": r["result"], "winner_group": r["winner_group"],
                       "score": r["score"]} for r in rows],
    }
    return hashlib.sha256(
        json.dumps(preimage, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def build_result(game_id: str, game_uid: str, opponent: str, rows: list,
                 final_result: dict, opp_repos: dict | None = None) -> dict:
    """The emailed final_game_result (series aggregate). Key order mirrors anrbj666's."""
    confirmed = bool(rows) and all(r.get("audit", {}).get("log_verified") for r in rows)
    mutual = {"sha256": mutual_agreement_sha(game_id, rows, final_result), "confirmed": confirmed}
    return {
        "_schema": ("Summary and final result for the WHOLE series between two teams: "
                    "per-sub-game scores + aggregate; identity lives in the declaration."),
        "schema_version": "1.1",
        "report_type": "final_game_result",
        "game_id": game_id, "game_uid": game_uid,
        "links": {"declaration": f"declaration_{game_id}.json",
                  "config": f"config_{game_id}_g<NN>.json",
                  "log": f"log_{game_id}_g<NN>.json", "result": f"result_{game_id}.json",
                  "github": {"vibecode": OUR_REPOS, opponent: opp_repos or {}}},
        "timezone": "Asia/Jerusalem",
        "groups": sorted(["vibecode", opponent]),
        "num_sub_games": len(rows),
        "sub_games": rows,
        "final_result": final_result,
        "mutual_agreement": mutual,
    }


def write_artifact(obj: dict, path: Path) -> Path:
    """Write a repo artifact: pretty-printed (indent 2, insertion order) like anrbj666's."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def update_counted_ledger(ledger_path: Path, *, game_id: str, game_uid: str, opponent: str,
                          result_obj: dict, message_id: str | None,
                          our_counted_before: int) -> dict:
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
        "game_id": game_id, "game_uid": game_uid, "opponent": opponent,
        "winner_group": fr["winner_group"], "total_score": fr["total_score"],
        "sub_games_won": fr["sub_games_won"],
        "diversity_reward_applied": fr["diversity_reward_applied"],
        "mutual_agreement": result_obj["mutual_agreement"],
        "report_message_id": message_id, "reported_at": now_iso(),
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
    subject = (f"P2P league SERIES result - {result['game_id']} - "
               f"winner={fr['winner_group']} - {score_str}")
    msg = MIMEMultipart()
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    att = MIMEApplication(body.encode("utf-8"), _subtype="json")
    att.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(att)
    return gmail_api_send(msg, load_oauth_credentials(token_path))
