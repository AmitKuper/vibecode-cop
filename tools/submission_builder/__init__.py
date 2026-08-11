"""Course submission-form builder — see tools/submission_builder/README.md."""

from tools.submission_builder.builder import (
    build_submission,
    compute_totals,
    load_games,
    unfilled_placeholders,
)

__all__ = ["build_submission", "compute_totals", "load_games", "unfilled_placeholders"]
