"""What the opponent told us about themselves, gathered from every place they say it.

Peers put the same fact in different places and under different names. nis-yar1
seal `counted_games` and their `github_commit` in the Step-0 RECORD while their
negotiate identity carries neither; we read only the identity, so we filed their
prior-series count as 0 and their commit as "unknown" while their own report
said 1 and named the sha (2026-08-16). najamjad hit the mirror image of this
from the other side: they looked for a record typed `system_spec`, we spell it
`step_zero`, so they recorded OUR commit as "unknown" for six sub-games.

The lesson both ways: read every source the peer might have used, and prefer
what they SEALED over what they merely asserted. These numbers end up in both
teams' counted reports, where a disagreement is what a grader notices.
"""

from __future__ import annotations

#: Spellings peers have actually used for their prior counted-series count.
COUNT_KEYS = ("counted_games_played", "counted_matches_played", "counted_games")
#: Payload `type` values peers use for the sealed Step-0 record.
STEP_ZERO_TYPES = ("step_zero", "system_spec")


def step_zero_payload(opp_records: list | None) -> dict:
    """Their sealed Step-0 payload, whatever they called it ({} if absent)."""
    for record in opp_records or []:
        payload = (record or {}).get("payload") or {}
        if payload.get("type") in STEP_ZERO_TYPES:
            return payload
    return {}


def counted_played(identity: dict | None, sealed: dict | None) -> int | None:
    """Their prior counted-series count; None when they never stated one.

    None is not 0: "they did not say" and "they said zero" are different claims,
    and only the second belongs in a report as fact.
    """
    for source in (sealed or {}, identity or {}):
        for key in COUNT_KEYS:
            value = source.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.strip().isdigit():
                return int(value)
    return None


def github_commit(identity: dict | None, sealed: dict | None) -> str:
    """Their repo HEAD for the role they played; the SEALED value wins."""
    for source in (sealed or {}, identity or {}):
        value = source.get("github_commit")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unknown"


def hardware_spec(identity: dict | None, sealed: dict | None) -> dict:
    """Their declared machine, from the identity or the sealed `spec` field."""
    for candidate in ((identity or {}).get("hardware_spec"), (sealed or {}).get("spec")):
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


def series_counted_played(played: list | None) -> int:
    """Their prior counted count from the first window that states one (0 if none)."""
    for window in played or []:
        n = counted_played(window.get("opp_identity"), step_zero_payload(window.get("opp_records")))
        if n is not None:
            return n
    return 0
