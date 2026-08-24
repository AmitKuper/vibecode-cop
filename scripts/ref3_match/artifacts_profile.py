"""Result snapshot + opponent-profile auto-save (split from artifacts_io)."""

from __future__ import annotations

import json as _json
from pathlib import Path

from ref3_match.runtime_cfg import REPO_ROOT


def _write_result(result: dict) -> Path:
    out_dir = REPO_ROOT / "reports" / "ref3_matches"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "last_match_result.json"
    path.write_text(_json.dumps(result, indent=2), encoding="utf-8")
    return path


def _save_opponent_profile(opp: str, played_profile: str | None = None) -> None:
    """Save the exact config used to play this opponent: config/opponents/<opp>/.

    When the match was launched from a NAMED profile (--config) whose directory
    name differs from the opponent's group_id, that profile IS the played config —
    creating a sibling dir from base config would plant a misleading record
    (bench finding vs peersim01, 2026-08-13). Skip the auto-save in that case.
    """
    try:
        import shutil

        if played_profile and played_profile != opp:
            prof_dir = REPO_ROOT / "config" / "opponents" / str(played_profile)
            if prof_dir.is_dir():
                return  # the played profile already records this pairing's config
        prof = REPO_ROOT / "config" / "opponents" / opp
        prof.mkdir(parents=True, exist_ok=True)
        for f in ("game.json", "runtime.toml"):
            src = REPO_ROOT / "config" / f
            # NEVER overwrite an existing profile file: the base copy lacks the
            # profile's own keys ([protocol] scent_model/move_policy, opponent URLs) —
            # the auto-save clobbered the imreeyal profile with anrbj666 defaults
            # (live finding, 2026-08-10 friendly; restored from git).
            if src.is_file() and not (prof / f).exists():
                shutil.copyfile(src, prof / f)
        print(
            f"[match] saved config profile used vs {opp} -> config/opponents/{opp}/ "
            f"(existing profile files preserved)"
        )
    except Exception as exc:
        print(f"[match] WARN could not save opponent config ({type(exc).__name__}: {exc})")
