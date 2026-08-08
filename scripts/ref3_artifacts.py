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


def _sha(obj: object) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def now_iso() -> str:
    from datetime import datetime
    return datetime.now(UTC).isoformat()


def score_series(sub_games: list, opponent: str, cop_commit: str, game_id: str) -> tuple:
    """Return (rows, final_result) in the final_game_result schema.

    Appendix-F scoring: capture -> cop 20 / thief 5; survival -> thief 10 / cop 5.
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
        rows.append({
            "audit": {"log_verified": bool(sg.get("audit_ok")), "tampered": False},
            "ended_at": sg.get("ended_at", ""),
            "github_commit": {"vibecode": cop_commit, opponent: "unknown"},
            "log_files": {"vibecode": f"log_{game_id}_g{n:02d}.json",
                          opponent: f"log_{game_id}_g{n:02d}.json"},
            "result": sg.get("outcome"),
            "roles": {"vibecode": role, opponent: "thief" if role == "police" else "police"},
            "score": {"vibecode": us, opponent: them},
            "started_at": sg.get("started_at", ""),
            "sub_game_number": n, "tie": False,
            "tokens": {"vibecode": 0, opponent: 0},
            "winner_group": "vibecode" if us > them else opponent,
        })
    final_result = {
        "diversity_reward_applied": {"vibecode": False, opponent: False},
        "first_meeting_between_groups": True,
        "games_played_including_this": {"vibecode": 0, opponent: 0},
        "series_tie": tot_us == tot_them,
        "sub_games_won": {"vibecode": won_us, opponent: won_them},
        "ties": 0,
        "tokens_total_series": {"vibecode": 0, opponent: 0},
        "total_score": {"vibecode": tot_us, opponent: tot_them},
        "winner_group": ("vibecode" if tot_us > tot_them
                         else opponent if tot_them > tot_us else None),
    }
    return rows, final_result


def build_config(game_id: str, game_uid: str, sub_game: int, setting: str, opponent: str) -> dict:
    board = {"axis_origin_corner": "top-left", "axis_start_index": 0, "cop_start": [0, 0],
             "grid_size": 7, "num_agents": 2, "thief_start": [3, 3]}
    movement = {"max_barriers": 14, "max_moves": 35,
                "move_set": ["N", "S", "E", "W", "STAY"], "survival_threshold": 35}
    league = {"diversity_reward": 10, "max_games_per_team": 10, "min_games_to_pass": 2,
              "num_games": 6, "response_timeout_sec": 30, "token_budget_per_series": 200000,
              "watchdog_timeout_sec": 60}
    pher = {"min_center_intensity": 0.5, "pheromone_center_intensity": 0.9,
            "pheromone_decay": 0.1, "pheromone_grid_size": 5}
    rate = {"concurrent_requests": 2, "max_retries": 3, "queue_depth": 100,
            "requests_per_minute": 30, "retry_backoff_sec": 5}
    scoring = {"capture_cop": 20, "capture_thief": 5, "survival_cop": 5,
               "survival_thief": 10, "technical_loss": 0, "tie_score": 2}
    world = {"hint_max_words": 15, "map_area": setting}
    params = {"board_and_agents": board, "movement_and_barriers": movement,
              "network_and_league": league, "pheromones": pher, "scoring": scoring, "world": world}
    return {
        "_schema": "p2p-police-artifacts",
        "agreed_between": sorted(["vibecode", opponent]),
        "board_and_agents": board,
        "config_name": f"config_{game_id}_g{sub_game:02d}.json",
        "config_sha256": _sha(params),
        "game_id": game_id, "game_uid": game_uid,
        "links": OUR_REPOS,
        "movement_and_barriers": movement,
        "network_and_league": league,
        "pheromones": pher,
        "rate_limiter_gatekeeper": rate,
        "report_type": "config", "schema_version": "1.3",
        "scoring": scoring, "sub_game_number": sub_game, "world": world,
    }


def build_log(game_id: str, game_uid: str, sub_game: int, role: str, opponent: str,
              our_records: list, opp_records: list, summary: dict,
              github_commit: str) -> dict:
    step_zero = {
        "commit": _sha({"type": "step_zero", "sub_game": sub_game, "role": role}),
        "nonce": "0" * 32,
        "payload": {"declaration_ref": f"declaration_{game_id}.json",
                    "github_commit": github_commit, "group_id": "vibecode",
                    "role": role, "step": 0, "sub_game_number": sub_game, "type": "step_zero"},
    }
    return {
        "_schema": "p2p-police-artifacts",
        "game_id": game_id, "game_uid": game_uid,
        "links": {"config": f"config_{game_id}_g{sub_game:02d}.json",
                  "declaration": f"declaration_{game_id}.json",
                  "log": f"log_{game_id}_g{sub_game:02d}.json",
                  "result": f"result_{game_id}.json"},
        "opponent_records": opp_records,
        "records": [step_zero] + our_records,
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
                      opp_identity: dict | None = None) -> dict:
    hw = _hardware_spec()
    ours = {
        "code_version": "1.00", "counted_games_played": 0, "github_commit": cop_commit,
        "group_id": "vibecode", "group_name": "vibecode",
        "hardware_spec": hw, "hardware_spec_sha256": _sha(hw) if hw else "",
        "llm_model": "role-specific-recurrent-policy",
        "mcp_servers": OUR_MCP, "members": members, "repos": OUR_REPOS,
        "signature": f"sha256:{_sha({'group_id': 'vibecode', 'commit': cop_commit})}",
    }
    theirs = opp_identity or {"group_id": opponent, "group_name": opponent,
                              "counted_games_played": 0, "github_commit": "unknown",
                              "hardware_spec": {}, "hardware_spec_sha256": "",
                              "llm_model": "unknown", "mcp_servers": {}, "members": [],
                              "repos": {}, "signature": "undeclared"}
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


def build_result(game_id: str, game_uid: str, opponent: str, rows: list,
                 final_result: dict, cop_commit: str) -> dict:
    """The emailed final_game_result (series aggregate)."""
    mutual = {"confirmed": False,
              "sha256": _sha({"game_uid": game_uid, "rows": rows, "final": final_result})}
    return {
        "_schema": ("Summary and final result for the WHOLE series between two teams: "
                    "per-sub-game scores + aggregate; identity lives in the declaration."),
        "final_result": final_result,
        "game_id": game_id, "game_uid": game_uid,
        "groups": sorted(["vibecode", opponent]),
        "links": {"config": f"config_{game_id}_g<NN>.json",
                  "declaration": f"declaration_{game_id}.json",
                  "github": {"vibecode": OUR_REPOS, opponent: {}},
                  "log": f"log_{game_id}_g<NN>.json", "result": f"result_{game_id}.json"},
        "mutual_agreement": mutual,
        "num_sub_games": len(rows), "report_type": "final_game_result",
        "schema_version": "1.1", "sub_games": rows, "timezone": "Asia/Jerusalem",
    }


def write_artifact(obj: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True), encoding="utf-8")
    return path


def email_result(result: dict, recipient: str, filename: str, token_path: Path) -> str:
    """Email the result: body = canonical bytes, one attachment = same bytes."""
    from email.mime.application import MIMEApplication
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    from league_manager.reports.gmail_send import gmail_api_send, load_oauth_credentials

    body = canonical_json(result)
    fr = result["final_result"]
    subject = (f"[vibecode] friendly {result['game_id']} "
               f"{fr.get('total_score')} winner={fr.get('winner_group')}")
    msg = MIMEMultipart()
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    att = MIMEApplication(body.encode("utf-8"), _subtype="json")
    att.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(att)
    return gmail_api_send(msg, load_oauth_credentials(token_path))
