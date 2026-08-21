"""Enforce the project's 150-line-per-file rule as a ratchet.

The rule is documented in the README and was previously enforced by nothing, so
files drifted over it silently. Ruff cannot express it (it caps line *length*,
not line *count*), hence this gate.

Ratchet, not amnesty: files already over the limit are listed in ALLOWED with a
reason, and each entry pins the size it was granted at. A listed file that GROWS
fails, a NEW oversize file fails, and a listed file that has since been split is
reported so the entry can be deleted. The list only ever shrinks.

    python scripts/check_file_size.py          # gate (exit 1 on violation)
    python scripts/check_file_size.py --list   # show every file over the limit
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

LIMIT = 150
REPO_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".venv", ".git", "__pycache__", "node_modules", "external", ".claude", "htmlcov"}

#: path -> (max_lines_allowed, why it is exempt). Shrink this list; never grow it.
ALLOWED: dict[str, tuple[int, str]] = {
    "cop_worker/domain/transition.py": (
        295,
        "apply_joint_action is the single source of truth for game physics and must "
        "produce byte-identical results to the opponent's engine; splitting the "
        "sequential rule application across files would fragment that invariant for "
        "a cosmetic line count. Pure helpers were already extracted to "
        "transition_geometry.py and transition_scent.py.",
    ),
    "cop_worker/net_gateway.py": (
        170,
        "Single outbound-call policy surface: pacing, retry, breaker.",
    ),
    "cop_worker/gui/hub_api.py": (195, "One read-only hub API surface incl. human-play history."),
    "cop_worker/protocol/reference_v3/session.py": (
        165,
        "One wire session; the four tools are one protocol unit.",
    ),
    "scripts/ref3_match/artifacts_io.py": (
        170,
        "One emission unit: every league artifact written in a single pass.",
    ),
    "scripts/ref3_match/subgame_settle.py": (
        170,
        "Audit settlement is one transaction: verify, refine, snapshot, row.",
    ),
    "scripts/ref3_match/subgame_turns.py": (
        170,
        "The turn loop; call-site ordering is pinned by tests.",
    ),
    "scripts/ref3_match/subgame_setup.py": (
        170,
        "Handshake + step-0 seal, one atomic sequence (grew by the kit §5 series-label fold).",
    ),
    "scripts/ref3_match/series_split.py": (
        155,
        "One series lifecycle over role workers (grew by the kit §5 series-label fold).",
    ),
    "scripts/ref3_match/role_worker.py": (155, "Worker entry point: stdio protocol loop."),
    "cop_worker/rl/search_policy.py": (175, "One decision sequence; override priority order."),
    "scripts/barrier_distill/collect.py": (160, "One research collection recipe (non-runtime)."),
    "scripts/pocketer_lab.py": (
        180,
        "One lab scenario (non-runtime): the scripted adaptive pocketer and both "
        "thief arms are a single reproducible experiment.",
    ),
    "cop_worker/gui/hub_page.py": (
        200,
        "A single HTML/JS page template in a string: its line count is markup, "
        "not Python complexity. The page logic itself is small per view.",
    ),
    "cop_worker/gui/replay_page.py": (
        175,
        "Same as hub_page: one HTML/JS page template in a string. Splitting the "
        "stylesheet from the markup it styles would hide the layout contract "
        "(one column width drives every block) across two files.",
    ),
    "tests/test_submission_builder.py": (160, "Table-driven fixtures for the submission form."),
    "tests/test_split_architecture.py": (160, "End-to-end split-architecture scenario."),
    "tests/test_game_record.py": (
        180,
        "The full record chain (capture/merge/timeline/API/archive) in one suite.",
    ),
    "tests/test_gui_routes_and_stepping.py": (
        180,
        "One behavioral suite over the replay stepping contract: CLI loop, API "
        "ordering, page wiring - splitting it would scatter one contract.",
    ),
}


def oversize_files() -> dict[str, int]:
    found: dict[str, int] = {}
    for path in REPO_ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            n = sum(1 for _ in path.open("r", encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if n > LIMIT:
            found[path.relative_to(REPO_ROOT).as_posix()] = n
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="print every file over the limit")
    args = ap.parse_args()

    found = oversize_files()
    if args.list:
        for rel, n in sorted(found.items(), key=lambda kv: -kv[1]):
            mark = "allowed" if rel in ALLOWED else "VIOLATION"
            print(f"{n:5}  {mark:9} {rel}")
        return 0

    violations = [
        f"{rel} is {n} lines (limit {LIMIT})"
        for rel, n in sorted(found.items())
        if rel not in ALLOWED
    ]
    violations += [
        f"{rel} grew to {n} lines (allowance {ALLOWED[rel][0]})"
        for rel, n in sorted(found.items())
        if rel in ALLOWED and n > ALLOWED[rel][0]
    ]
    stale = [rel for rel in ALLOWED if rel not in found]

    for v in violations:
        print(f"FAIL  {v}")
    for rel in sorted(stale):
        print(f"NOTE  {rel} is now within the limit - delete its ALLOWED entry")
    if violations:
        print(f"\n{len(violations)} file(s) break the 150-line rule.")
        print("Split them, or add a justified ALLOWED entry if the file is genuinely atomic.")
        return 1
    print(f"OK  {len(found)} file(s) over {LIMIT} lines, all with a justified allowance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
