"""Settlement guard, league email, and the counted ledger — the reporting tail."""

from __future__ import annotations

from ref3_match.artifacts_io import _emit_files
from ref3_match.runtime_cfg import REPO_ROOT

EXPECTED_SUB_GAMES = 6


def _report_and_ledger(ctx: dict, args) -> None:
    """File the report and ledger ONLY for a fully-settled series (rule 32/35 discipline)."""
    from ref3_artifacts import email_result, update_counted_ledger

    played, result_obj = ctx["played"], ctx["result_obj"]
    # Settlement guard: a report is filed ONLY when the WHOLE series settled — all six windows
    # played AND each audit "Verified OK". A partial/failed series never auto-files a broken or
    # empty result to the league (matches anrbj666's runner). Re-run the missing windows, then
    # report. Artifacts are always kept locally regardless.
    n_settled = sum(1 for sg in played if sg.get("audit_ok"))
    series_complete = len(played) == EXPECTED_SUB_GAMES and n_settled == EXPECTED_SUB_GAMES
    mid = None
    if not series_complete:
        print(
            f"[match] REPORT WITHHELD (settlement guard): series not fully settled — "
            f"{n_settled}/{EXPECTED_SUB_GAMES} Verified OK, {len(played)}/{EXPECTED_SUB_GAMES} "
            f"windows played. No email, no ledger entry. Artifacts kept locally; re-run the "
            f"missing/failed windows before reporting."
        )
    elif not args.no_email:
        try:
            token = REPO_ROOT / "secrets" / "gmail" / "token.json"
            mid = email_result(result_obj, args.report_to, f"result_{ctx['game_id']}.json", token)
            print(f"[match] emailed result ONLY to {args.report_to} (id={mid})")
        except Exception as exc:
            print(f"[match] email FAILED ({type(exc).__name__}: {str(exc)[:140]})")
    # League ledger: record ONLY a fully-settled counted series (rules 37-38, the counted tracker).
    if ctx["counted"] and series_complete:
        ledger = update_counted_ledger(
            ctx["results_dir"] / "counted_series.json",
            game_id=ctx["game_id"],
            game_uid=ctx["game_uid"],
            opponent=args.opponent_group,
            result_obj=result_obj,
            message_id=mid,
            our_counted_before=ctx["our_counted"],
        )
        print(
            f"[match] counted ledger updated: counted_games_played={ledger['counted_games_played']} "
            f"(results/counted_series.json)"
        )


def _emit_artifacts(result: dict, args) -> None:
    """Write the four league artifacts to the repo; email ONLY the result."""
    _report_and_ledger(_emit_files(result, args), args)
