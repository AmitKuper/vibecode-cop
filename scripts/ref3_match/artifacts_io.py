"""League artifact emission: per-gamelet configs/logs, declaration, result object."""

from __future__ import annotations

from league_artifacts import opponent_facts

from ref3_match.artifacts_profile import (  # noqa: F401  (re-exports)
    _save_opponent_profile,
    _write_result,
)
from ref3_match.runtime_cfg import REPO_ROOT, _git_head


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
    label = getattr(args, "series_label", "") or None
    game_id = derive_game_id("vibecode", opp, label)
    game_uid = derive_game_uid(default_terms({"setting": args.setting}), "vibecode", opp, label)
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
        # Companion game record: both sides' full per-step experience (actual
        # wire scent/hints), replayable in the viewer. Observational only.
        from ref3_match.game_record import build_game_record

        write_artifact(
            build_game_record(game_id, game_uid, n, sg["role"], opp, sg),
            results_dir / f"record_{game_id}_g{n:02d}.json",
        )
    # The opponent's declared identity (rules 49/53) — repos, counted count — from their greeting.
    opp_ids = [sg.get("opp_identity") or {} for sg in played if sg.get("opp_identity")]
    opp_repos = next((i.get("repos") for i in opp_ids if i.get("repos")), {})
    # Their count can ride the negotiate identity OR the sealed Step-0 record, under
    # three spellings - league_artifacts.opponent_facts knows all of them.
    opp_counted = opponent_facts.series_counted_played(played)
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
    # PER-RUN archive: result_<game_id>.json is one file per game_id, so each
    # series used to OVERWRITE the last - three rstabcde friendlies and the
    # nis-yar1 friendlies vanished under their counted results (found
    # 2026-08-17). Every run now also lands in results/history/, timestamped
    # from its first window, and is never overwritten.
    stamp = (starts[0] or "")[:19].replace(":", "").replace("-", "").replace("T", "-") or "unknown"
    write_artifact(result_obj, results_dir / "history" / f"result_{game_id}_{stamp}.json")
    # Records AND configs rotate per game_id exactly like logs - archive both
    # per-run, so EVERY run (friendly rematches included) stays reconstructable
    # (App-F mandatory instruction 3: a distinct config name per game).
    import shutil

    (config_dir / "history").mkdir(parents=True, exist_ok=True)
    for sg in played:
        n = sg["sub_game"]
        rec = results_dir / f"record_{game_id}_g{n:02d}.json"
        if rec.is_file():
            shutil.copyfile(rec, results_dir / "history" / f"{rec.stem}_{stamp}.json")
        cfg = config_dir / f"config_{game_id}_g{n:02d}.json"
        if cfg.is_file():
            shutil.copyfile(cfg, config_dir / "history" / f"{cfg.stem}_{stamp}.json")
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
