#!/usr/bin/env python3
"""Run and independently verify the real clean-tree two-process counted series."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT.parent
COP_REPO = WORKSPACE / "vibecode-cop"
THIEF_REPO = WORKSPACE / "vibecode-thief"


def _python(repo: Path) -> Path:
    candidate = repo / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not candidate.is_file():
        raise RuntimeError(f"repository environment Python not found: {candidate}")
    return candidate


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_listener(port: int, process: subprocess.Popen, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"thief server exited before listening (exit {process.returncode})")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"thief server did not listen on port {port} within {timeout_s}s")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contains_private_nonce_key(value) -> bool:
    if isinstance(value, dict):
        return any(
            key in {"nonce", "nonces"} or _contains_private_nonce_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_private_nonce_key(item) for item in value)
    return False


def _verify_artifacts(output: Path, cop_sha: str, thief_sha: str) -> dict:
    if str(COP_REPO) not in sys.path:
        sys.path.insert(0, str(COP_REPO))
    from agent.audit.audit_summary import SignedAuditSummary, verify_audit_summary
    from agent.audit.result_consensus import (
        SignedResultAgreement,
        verify_bilateral_consensus,
        verify_result_agreement_signature,
    )
    from agent.step0.declaration import SignedDeclaration
    from agent.step0.signing import verify

    active_paths = list((output / "cop").glob("result_agreement_series_*.json"))
    passive_paths = list((output / "thief").glob("result_agreement_series_*_passive.json"))
    if len(active_paths) != 1 or len(passive_paths) != 1:
        raise RuntimeError(
            f"expected one active/passive agreement, got {len(active_paths)}/{len(passive_paths)}"
        )
    active_path, passive_path = active_paths[0], passive_paths[0]
    active = json.loads(active_path.read_text(encoding="utf-8"))
    passive = json.loads(passive_path.read_text(encoding="utf-8"))
    evidence = active["verification_evidence"]
    steps = evidence["step0"]
    if len(steps) != 6:
        raise RuntimeError(f"expected six Step-0 evidence pairs, got {len(steps)}")

    local_keys: dict[str, bytes] = {}
    remote_keys: dict[str, bytes] = {}
    local_profile_hashes: set[str] = set()
    remote_profile_hashes: set[str] = set()
    for item in steps:
        local = SignedDeclaration.from_dict(item["local_signed_declaration"])
        remote = SignedDeclaration.from_dict(item["remote_signed_declaration"])
        for signed, expected_sha in ((local, cop_sha), (remote, thief_sha)):
            declaration = signed.declaration
            public = bytes.fromhex(declaration.public_key_hex)
            signature = bytes.fromhex(signed.signature_hex)
            if not verify(public, declaration.canonical_bytes(), signature):
                raise RuntimeError(f"invalid Step-0 signature for {declaration.game_uid}")
            if declaration.git_sha != expected_sha:
                raise RuntimeError(
                    f"Step-0 git SHA mismatch for {declaration.model_role}: "
                    f"{declaration.git_sha} != {expected_sha}"
                )
        game_id = local.declaration.game_uid
        if remote.declaration.game_uid != game_id:
            raise RuntimeError("Step-0 peers disagree on game UID")
        local_keys[game_id] = bytes.fromhex(local.declaration.public_key_hex)
        remote_keys[game_id] = bytes.fromhex(remote.declaration.public_key_hex)
        local_profile_hashes.add(local.declaration.adapter_mapping_hash)
        remote_profile_hashes.add(remote.declaration.adapter_mapping_hash)
    if len(local_profile_hashes) != 1 or len(remote_profile_hashes) != 1:
        raise RuntimeError("adaptive profile changed during the counted series")

    local_audits = [
        SignedAuditSummary.from_dict(item) for item in evidence["local_signed_audit_summaries"]
    ]
    remote_audits = [
        SignedAuditSummary.from_dict(item) for item in evidence["remote_signed_audit_summaries"]
    ]
    if len(local_audits) != 6 or len(remote_audits) != 6:
        raise RuntimeError("bilateral audit evidence is not exactly 6+6 summaries")
    for summaries, keys in ((local_audits, local_keys), (remote_audits, remote_keys)):
        for signed in summaries:
            summary = signed.summary
            if summary.audit_status != "PASSED":
                raise RuntimeError(f"non-passing audit for {summary.game_uid}")
            if not verify_audit_summary(signed, keys[summary.game_uid]):
                raise RuntimeError(f"invalid audit signature for {summary.game_uid}")

    local_result = SignedResultAgreement.from_dict(evidence["local_signed_result_agreement"])
    remote_result = SignedResultAgreement.from_dict(evidence["remote_signed_result_agreement"])
    last_game_id = sorted(local_keys)[-1]
    if not verify_result_agreement_signature(local_result, local_keys[last_game_id]):
        raise RuntimeError("active ResultAgreement signature is not Step-0-bound")
    if not verify_result_agreement_signature(remote_result, remote_keys[last_game_id]):
        raise RuntimeError("passive ResultAgreement signature is not Step-0-bound")
    verify_bilateral_consensus(local_result, remote_result)
    if active["agreement"] != passive["agreement"]:
        raise RuntimeError("active and passive agreement artifacts differ")
    agreement = local_result.agreement
    if len(agreement.gamelet_outcomes) != 6:
        raise RuntimeError("ResultAgreement is not exactly six gamelets")
    required_tokens = {"prompt_tokens", "completion_tokens", "total_tokens"}
    if set(agreement.token_totals) != required_tokens:
        raise RuntimeError("series token totals missing from ResultAgreement")
    if any(set(outcome.token_totals) != required_tokens for outcome in agreement.gamelet_outcomes):
        raise RuntimeError("gamelet token totals missing from ResultAgreement")
    if _contains_private_nonce_key(active):
        raise RuntimeError("public result evidence contains private nonce-value keys")

    ledgers = list((output / "cop").rglob("league_ledger.json"))
    peer_ledgers = list((output / "thief").rglob("league_ledger.json"))
    if len(ledgers) != 1 or len(peer_ledgers) != 1:
        raise RuntimeError("expected one independent league ledger per process")
    cop_entries = json.loads(ledgers[0].read_text(encoding="utf-8")).get("entries", [])
    thief_entries = json.loads(peer_ledgers[0].read_text(encoding="utf-8")).get("entries", [])
    if len(cop_entries) != 1 or len(thief_entries) != 1:
        raise RuntimeError("expected one counted ledger entry per role")
    cop_entry, thief_entry = cop_entries[0], thief_entries[0]
    if cop_entry.get("opponent_id") != "THIF1234":
        raise RuntimeError("cop ledger does not identify the independent thief peer")
    if thief_entry.get("opponent_id") != "COPP1234":
        raise RuntimeError("thief ledger does not identify the independent cop peer")
    shared_fields = (
        "match_id",
        "counted",
        "declaration_hash",
        "result_hash",
        "timestamp_utc",
        "both_result_signatures",
        "report_delivery_ids",
        "previous_entry_hash",
    )
    cop_consensus = {key: cop_entry.get(key) for key in shared_fields}
    thief_consensus = {key: thief_entry.get(key) for key in shared_fields}
    if cop_consensus != thief_consensus:
        raise RuntimeError("independent league ledgers disagree on shared match facts")
    ledger_consensus_sha256 = hashlib.sha256(
        json.dumps(cop_consensus, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    cop_mail = (output / "cop_fake_gmail.jsonl").read_text(encoding="utf-8").splitlines()
    thief_mail = (output / "thief_fake_gmail.jsonl").read_text(encoding="utf-8").splitlines()
    if len(cop_mail) != 1 or len(thief_mail) != 1:
        raise RuntimeError("expected one independent fake acceptance Gmail record per role")
    for line in cop_mail + thief_mail:
        if json.loads(line).get("delivery_kind") != "FAKE_ACCEPTANCE_ONLY":
            raise RuntimeError("acceptance Gmail record is not explicitly marked fake")

    return {
        "status": "PASS",
        "series_id": agreement.game_uid,
        "gamelets": 6,
        "step0_signatures_verified": 12,
        "audit_signatures_verified": 12,
        "result_signatures_verified": 2,
        "cop_git_sha": cop_sha,
        "thief_git_sha": thief_sha,
        "active_profile_hash": next(iter(local_profile_hashes)),
        "passive_profile_hash": next(iter(remote_profile_hashes)),
        "agreement_hash": agreement.agreement_hash(),
        "active_artifact": str(active_path),
        "active_artifact_sha256": _sha256(active_path),
        "passive_artifact": str(passive_path),
        "passive_artifact_sha256": _sha256(passive_path),
        "cop_ledger_sha256": _sha256(ledgers[0]),
        "thief_ledger_sha256": _sha256(peer_ledgers[0]),
        "ledger_consensus_sha256": ledger_consensus_sha256,
        "fake_gmail_records": 2,
        "real_gmail_status": "EXTERNAL_PENDING",
        "public_nonce_value_keys": 0,
        "token_totals": agreement.token_totals,
    }


def run(output: Path) -> dict:
    if not COP_REPO.is_dir() or not THIEF_REPO.is_dir():
        raise RuntimeError("companion cop/thief repositories were not found")
    for repo in (COP_REPO, THIEF_REPO):
        status = subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=repo,
            text=True,
        )
        if status.strip():
            raise RuntimeError(f"counted acceptance requires a clean repository: {repo}")
    cop_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=COP_REPO, text=True).strip()
    thief_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=THIEF_REPO, text=True
    ).strip()

    if output.exists():
        if any(output.iterdir()):
            raise RuntimeError(f"acceptance output directory is not empty: {output}")
    else:
        output.mkdir(parents=True)
    thief_port = _free_port()
    secret = "local-acceptance-shared-secret-2026"
    thief_stdout = (output / "thief_stdout.log").open("w", encoding="utf-8")
    thief_stderr = (output / "thief_stderr.log").open("w", encoding="utf-8")
    thief_env = {**os.environ, "GROUP_ID": "THIF1234"}
    cop_env = {**os.environ, "GROUP_ID": "COPP1234"}
    thief_cmd = [
        str(_python(THIEF_REPO)),
        "-m",
        "thief",
        "serve",
        "--mode",
        "counted",
        "--config",
        "thief/config.toml",
        "--host",
        "127.0.0.1",
        "--port",
        str(thief_port),
        "--peer-url",
        "http://127.0.0.1:1/mcp",
        "--secret",
        secret,
        "--games-dir",
        str(output / "thief"),
        "--acceptance-fake-gmail-outbox",
        str(output / "thief_fake_gmail.jsonl"),
    ]
    process = subprocess.Popen(
        thief_cmd,
        cwd=THIEF_REPO,
        env=thief_env,
        stdout=thief_stdout,
        stderr=thief_stderr,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        _wait_for_listener(thief_port, process)
        cop_cmd = [
            str(_python(COP_REPO)),
            "-m",
            "cop",
            "series",
            "--mode",
            "counted",
            "--config",
            "cop/config.toml",
            "--peer-url",
            f"http://127.0.0.1:{thief_port}",
            "--secret",
            secret,
            "--games-dir",
            str(output / "cop"),
            "--n-gamelets",
            "6",
            "--acceptance-fake-gmail-outbox",
            str(output / "cop_fake_gmail.jsonl"),
        ]
        completed = subprocess.run(
            cop_cmd,
            cwd=COP_REPO,
            env=cop_env,
            capture_output=True,
            text=True,
            timeout=240,
        )
        (output / "cop_stdout.log").write_text(completed.stdout, encoding="utf-8")
        (output / "cop_stderr.log").write_text(completed.stderr, encoding="utf-8")
        if completed.returncode != 0:
            raise RuntimeError(
                f"cop counted CLI failed with exit {completed.returncode}; "
                f"see {output / 'cop_stderr.log'}"
            )
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        thief_stdout.close()
        thief_stderr.close()
    return _verify_artifacts(output, cop_sha, thief_sha)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--json", type=Path, help="optional summary JSON path")
    args = parser.parse_args()
    if args.output_dir:
        output = args.output_dir.resolve()
        result = run(output)
    else:
        output = Path(tempfile.mkdtemp(prefix="cop_thief_acceptance_"))
        result = run(output)
    result["output_dir"] = str(output)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
