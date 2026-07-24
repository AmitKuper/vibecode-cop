"""Replay viewer and audit CLI for cop-vs-thief game logs.

Usage:
    python scripts/replay_viewer.py <log_file_or_dir>

Accepts either a single log_*.json file or a directory containing log_*.json files.
Prints integrity and commitment audit results, exits 0 if all OK, 1 if any tampered.
"""

import sys
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.mcp.log_replay import audit_log_commitments, load_log_json, verify_log_integrity


def audit_single(log_file: Path) -> bool:
    """Audit one log file. Returns True if OK, False if tampered."""
    print(f"Auditing {log_file.name}...")

    integrity = verify_log_integrity(log_file)
    sha = integrity.get("log_sha256", "?")[:12]
    if integrity.get("ok"):
        print(f"  Integrity:   OK  (sha256: {sha}...)")
    else:
        detail = integrity.get("details", "unknown error")
        print(f"  Integrity:   FAIL ({detail})")
        print(f"=== TAMPERED: {detail} ===")
        return False

    try:
        log_data = load_log_json(log_file)
    except Exception as exc:
        print(f"  Commitments: FAIL (could not parse log: {exc})")
        print(f"=== TAMPERED: could not parse log ===")
        return False

    commit_result = audit_log_commitments(log_data)
    verified = commit_result.get("verified", 0)
    failed = commit_result.get("failed", 0)
    total = verified + failed
    if commit_result.get("ok"):
        print(f"  Commitments: OK  ({verified}/{total} verified)")
        print("=== VERIFIED OK ===")
        return True
    else:
        print(f"  Commitments: FAIL ({failed} mismatches out of {total})")
        print(f"=== TAMPERED: commitment mismatch ===")
        return False


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/replay_viewer.py <log_file_or_dir>")
        sys.exit(1)

    target = Path(sys.argv[1])

    if target.is_dir():
        log_files = sorted(target.glob("log_*.json"))
        if not log_files:
            print(f"No log_*.json files found in {target}")
            sys.exit(1)
    elif target.is_file():
        log_files = [target]
    else:
        print(f"Path not found: {target}")
        sys.exit(1)

    all_ok = True
    for log_file in log_files:
        ok = audit_single(log_file)
        if not ok:
            all_ok = False
        print()

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
