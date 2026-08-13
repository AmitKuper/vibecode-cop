"""League artifact emission: per-gamelet configs/logs, declaration, result object."""

from __future__ import annotations

import json as _json
from pathlib import Path

from ref3_match.runtime_cfg import REPO_ROOT, _git_head


def _write_result(result: dict) -> Path:
    out_dir = REPO_ROOT / "reports" / "ref3_matches"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "last_match_result.json"
    path.write_text(_json.dumps(result, indent=2), encoding="utf-8")
    return path


def _save_opponent_profile(opp: str, played_profile: str | None = None) -> None:
    """Save the exact config used to play this opponent: config/opponents/<opp>/.

    When the match was launched from a NAMED profile (--config) whose directory
    name differs from the opponent's group_id, that profile IS the played config —
    creating a sibling dir from base config would plant a misleading record
    (bench finding vs peersim01, 2026-08-13). Skip the auto-save in that case.
    """
    try:
        import shutil

        if played_profile and played_profile != opp:
            prof_dir = REPO_ROOT / "config" / "opponents" / str(played_profile)
            if prof_dir.is_dir():
                return  # the played profile already records this pairing's config
        prof = REPO_ROOT / "config" / "opponents" / opp
        prof.mkdir(parents=True, exist_ok=True)
        for f in ("game.json", "runtime.toml"):
            src = REPO_ROOT / "config" / f
            # NEVER overwrite an existing profile file: the base copy lacks the
            # profile's own keys ([protocol] scent_model/move_policy, opponent URLs) —
            # the auto-save clobbered the imreeyal profile with anrbj666 defaults
            # (live finding, 2026-08-10 friendly; restored from git).
            if src.is_file() and not (prof / f).exists():
                shutil.copyfile(src, prof / f)
        print(
            f"[match] saved config profile used vs {opp} -> config/opponents/{opp}/ "
            f"(existing profile files preserved)"
        )
    except Exception as exc:
        print(f"[match] WARN could not save opponent config ({type(exc).__name__}: {exc})")


def _emit_files(result: dict, args) -> dict:
    """Write configs/logs/declaration/result; returns the scored context for reporting."""
    from ref3_artifacts import (
        build_config,
        build_declaration,
        build_log,
        build_result,
        score_series,
        write_artifact,
    )

    from cop_worker.protocol.reference_v3 import default_terms, derive_game_id, derive_game_uid

    opp = args.opponent_group
    _save_opponent_profile(opp, played_profile=getattr(args, "config", None))
    game_id = derive_game_id("vibecode", opp)
    game_uid = derive_game_uid(default_terms({"setting": args.setting}), "vibecode", opp)
    cop_commit = _git_head(REPO_ROOT)
    results_dir = REPO_ROOT / "results"
    config_dir = REPO_ROOT / "config" / "games"
    played = [sg for sg in result["sub_games"] if sg.get("our_records") is not None]
    for sg in played:
        n = sg["sub_game"]
        write_artifact(
            build_config(game_id, game_uid, n, args.setting, opp),
            config_dir / f"config_{game_id}_g{n:02d}.json",
        )
        write_artifact(
            build_log(
                game_id,
                game_uid,
                n,
                sg["role"],
                opp,
                sg["our_records"],
                sg["opp_records"],
                sg["summary"],
            ),
            results_dir / f"log_{game_id}_g{n:02d}.json",
        )
    # The opponent's declared identity (rules 49/53) — repos, counted count — from their greeting.
    opp_ids = [sg.get("opp_identity") or {} for sg in played if sg.get("opp_identity")]
    opp_repos = next((i.get("repos") for i in opp_ids if i.get("repos")), {})
    opp_counted = next(
        (
            i.get("counted_games_played")
            for i in opp_ids
            if i.get("counted_games_played") is not None
        ),
        0,
    )
    our_counted = getattr(args, "counted_played", 0)
    counted = getattr(args, "counted", False)
    rows, final_result = score_series(
        played, opp, game_id, our_played=our_counted, opp_played=opp_counted, counted=counted
    )
    members = [m.strip() for m in args.members.split(",") if m.strip()]
    starts = [sg.get("started_at", "") for sg in played]
    ends = [sg.get("ended_at", "") for sg in played]
    thief_commit = _git_head(REPO_ROOT.parent / "vibecode-thief")
    write_artifact(
        build_declaration(
            game_id,
            game_uid,
            opp,
            members,
            cop_commit,
            starts[0] if starts else "",
            ends[-1] if ends else "",
            opp_identity=(opp_ids[0] if opp_ids else None),
            our_counted=our_counted,
            thief_commit=thief_commit,
        ),
        results_dir / f"declaration_{game_id}.json",
    )
    result_obj = build_result(game_id, game_uid, opp, rows, final_result, opp_repos=opp_repos)
    write_artifact(result_obj, results_dir / f"result_{game_id}.json")
    print(
        f"[match] artifacts: {len(played)}x(config+log) + declaration + result "
        f"under results/ and config/games/"
    )
    print(f"[match] result: {final_result['total_score']} winner={final_result['winner_group']}")
    return {
        "played": played,
        "result_obj": result_obj,
        "final_result": final_result,
        "game_id": game_id,
        "game_uid": game_uid,
        "our_counted": our_counted,
        "counted": counted,
        "results_dir": results_dir,
    }
