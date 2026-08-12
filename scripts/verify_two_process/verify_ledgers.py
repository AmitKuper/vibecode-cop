"""Independent-ledger and fake-Gmail checks for the acceptance run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _verify_ledgers_and_mail(output: Path) -> tuple[list[Path], list[Path], str]:
    """League-ledger consensus + fake acceptance Gmail records (verbatim from
    the original ``_verify_artifacts`` body). Returns the two ledger path lists
    and the ledger consensus SHA-256."""
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

    return ledgers, peer_ledgers, ledger_consensus_sha256
