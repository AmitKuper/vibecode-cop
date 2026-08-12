"""Shared builders for the league-ledger test modules."""

from league_manager.league_ledger import LeagueLedger, LedgerEntry


def _entry(opponent_id: str, counted: bool, match_id: str = "") -> LedgerEntry:
    return LedgerEntry(
        opponent_id=opponent_id,
        match_id=match_id or f"match-{opponent_id}",
        counted=counted,
        declaration_hash="decl-hash",
        result_hash="result-hash",
        timestamp_utc="2026-01-01T00:00:00+00:00",
    )


def _ledger(tmp_path) -> LeagueLedger:
    return LeagueLedger(str(tmp_path / "ledger.json"))
