"""Replay viewer and audit CLI for cop-vs-thief game logs.

Usage:
    python scripts/replay_viewer.py <log_file_or_dir>

Accepts either a single log_*.json file or a directory containing log_*.json files.
Handles BOTH log formats: the internal gamelet log (h_commit records) and the
production reference-v3 wire log (records of {payload, nonce, commit}, incl.
opponent_records — both directions rehashed). Prints integrity and commitment
audit results, exits 0 if all OK, 1 if any tampered.
"""

import sys
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from cop_worker.mcp.log_replay import audit_log_commitments, load_log_json, verify_log_integrity


def _audit_reference_v3(doc: dict) -> dict:
    """Rehash every sealed record in a reference-v3 log (ours + opponent's)."""
    from cop_worker.protocol.reference_v3.hashing import reference_commit

    verified = failed = 0
    for side in ("records", "opponent_records"):
        for rec in doc.get(side) or []:
            body, nonce, claimed = rec.get("payload"), rec.get("nonce"), rec.get("commit")
            if not isinstance(body, dict) or not isinstance(nonce, str):
                failed += 1
                continue
            if reference_commit(body, nonce) == claimed:
                verified += 1
            else:
                failed += 1
    return {"ok": failed == 0 and verified > 0, "verified": verified, "failed": failed}


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
        print("=== TAMPERED: could not parse log ===")
        return False

    is_ref3 = isinstance(log_data.get("records"), list) and any(
        isinstance(r, dict) and "commit" in r and "payload" in r for r in log_data["records"]
    )
    commit_result = _audit_reference_v3(log_data) if is_ref3 else audit_log_commitments(log_data)
    verified = commit_result.get("verified", 0)
    failed = commit_result.get("failed", 0)
    total = verified + failed
    if commit_result.get("ok"):
        print(f"  Commitments: OK  ({verified}/{total} verified)")
        print("=== VERIFIED OK ===")
        return True
    else:
        print(f"  Commitments: FAIL ({failed} mismatches out of {total})")
        print("=== TAMPERED: commitment mismatch ===")
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
