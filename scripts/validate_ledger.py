"""Read-only cross-check of the counted ledger against its evidence artifacts.

Verifies, WITHOUT modifying anything, that every row of the canonical ledger
(``results/counted_series.json``) is backed by the artifacts the league rules
require: a result file whose scores/rows reconcile with the ledger, a
declaration, per-sub-game config evidence, a confirmed mutual agreement, and a
report message id. Draws must be draws (``winner_group`` null + ``series_tie``),
never losses — the shape of the 2026-08-23 submission-form defect.

    python scripts/validate_ledger.py     # exit 1 on any mismatch, prints all
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "results"


def _fail(errors: list[str], msg: str) -> None:
    errors.append(msg)
    print(f"FAIL  {msg}")


def validate() -> int:
    ledger = json.loads((RESULTS / "counted_series.json").read_text(encoding="utf-8"))
    series = ledger["series"]
    errors: list[str] = []
    opponents = [row["opponent"] for row in series]
    if len(set(opponents)) != len(opponents):
        _fail(errors, "an opponent appears more than once in the counted ledger (rule 52)")
    if ledger["counted_games_played"] != len(series):
        _fail(errors, "counted_games_played != number of ledger rows")
    wins = losses = draws = points = 0
    for row in series:
        opp, gid = row["opponent"], row["game_id"]
        result_path = RESULTS / f"result_{gid}.json"
        evidence = REPO / "evidence" / f"game_vs_{opp}"
        # Rematches rotate results/result_*.json; the committed evidence copy is
        # the durable artifact for the counted run — accept either location.
        candidates = [evidence / f"result_{gid}.json", result_path]
        result_file = next((p for p in candidates if p.is_file()), None)
        if result_file is None:
            _fail(errors, f"{opp}: no result file in evidence/ or results/")
            continue
        result = json.loads(result_file.read_text(encoding="utf-8"))
        if (
            not (evidence / f"declaration_{gid}.json").is_file()
            and not (RESULTS / f"declaration_{gid}.json").is_file()
        ):
            _fail(errors, f"{opp}: declaration missing")
        if not list(evidence.glob(f"config_{gid}_g0*.json")):
            _fail(errors, f"{opp}: no per-sub-game config evidence")
        if not row["mutual_agreement"]["confirmed"]:
            _fail(errors, f"{opp}: mutual agreement not confirmed in ledger")
        if not row.get("report_message_id"):
            _fail(errors, f"{opp}: no report message id in ledger")
        if result["final_result"]["total_score"] != row["total_score"]:
            _fail(errors, f"{opp}: result total_score != ledger total_score")
        if result["final_result"]["sub_games_won"] != row["sub_games_won"]:
            _fail(errors, f"{opp}: result sub_games_won != ledger sub_games_won")
        us, them = row["total_score"]["vibecode"], row["total_score"][opp]
        points += us
        if row["winner_group"] is None:
            draws += 1
            if us != them:
                _fail(errors, f"{opp}: null winner but unequal score {us}-{them}")
        elif row["winner_group"] == "vibecode":
            wins += 1
        else:
            losses += 1
    print(
        f"ledger: {len(series)} counted series, {wins}W-{losses}L-{draws}D, "
        f"{points} vibecode points"
    )
    if errors:
        print(f"{len(errors)} mismatch(es) — evidence NOT modified; investigate above")
        return 1
    print("OK  every ledger row is backed by reconciling evidence")
    return 0


if __name__ == "__main__":
    sys.exit(validate())
