"""Enforce the project's 150-line-per-file rule, strictly.

Every Python file in the repository must be at or under 150 lines. There is
no exemption list: the former ratchet's ALLOWED ledger was emptied on
2026-08-24 by refactoring every oversized module into cohesive sub-modules
(behavior pinned by the conformance/protocol/golden suites), and the gate is
now absolute so the debt cannot return.

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


def _iter_py_files() -> list[Path]:
    out = []
    for path in REPO_ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        out.append(path)
    return sorted(out)


def _line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list files over the limit")
    args = parser.parse_args()
    over = []
    for path in _iter_py_files():
        n = _line_count(path)
        if n > LIMIT:
            over.append((n, path.relative_to(REPO_ROOT).as_posix()))
    over.sort(reverse=True)
    if args.list:
        for n, rel in over:
            print(f"  {n:>4}  VIOLATION {rel}")
        if not over:
            print(f"OK  every Python file is at or under {LIMIT} lines")
        return 1 if over else 0
    if over:
        for n, rel in over:
            print(f"FAIL  {rel} is {n} lines (limit {LIMIT})")
        return 1
    print(f"OK  every Python file is at or under {LIMIT} lines (strict, no exemptions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
