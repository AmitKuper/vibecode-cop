"""Pin the declared constitution to the ``--config`` profile, not the base file.

``agreed_between`` names the two groups and is inside ``config_sha256``, so the
hash we put on the wire at Step-0 is per-pairing. The artifact builders used to
read ``config/game.json`` unconditionally, so every series declared whichever
pair the base file happened to name while the opponent profile's own game.json
was byte-diffed with the peer but never declared (found 2026-08-18).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from league_artifacts.core import (  # noqa: E402
    GAME_JSON_PATH,
    config_sha256,
    game_json_path,
    load_constitution,
)
from ref3_match.runtime_cfg import apply_runtime_config  # noqa: E402


def _sha_of(path: Path) -> str:
    import hashlib

    from cop_worker.protocol.reference_v3 import canonical_json

    payload = json.loads(path.read_text(encoding="utf-8"))
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def test_no_profile_declares_the_base_constitution():
    apply_runtime_config({})
    assert game_json_path() == GAME_JSON_PATH
    assert config_sha256() == _sha_of(GAME_JSON_PATH)


def test_profile_with_a_game_json_is_what_gets_declared(tmp_path):
    """A profile's own constitution wins — hash and agreed_between both follow."""
    profile = tmp_path / "opponents" / "someone"
    profile.mkdir(parents=True)
    payload = json.loads(GAME_JSON_PATH.read_text(encoding="utf-8"))
    payload["agreed_between"] = ["someone", "vibecode"]
    (profile / "game.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    apply_runtime_config({"profile": {"dir": str(profile)}})
    try:
        assert load_constitution()["agreed_between"] == ["someone", "vibecode"]
        assert config_sha256() == _sha_of(profile / "game.json")
        assert config_sha256() != _sha_of(GAME_JSON_PATH)
    finally:
        apply_runtime_config({})


def test_profile_without_a_game_json_falls_back_to_base(tmp_path):
    """Thin profiles that only override runtime.toml must still declare something."""
    thin = tmp_path / "thin"
    thin.mkdir()
    apply_runtime_config({"profile": {"dir": str(thin)}})
    try:
        assert game_json_path() == GAME_JSON_PATH
    finally:
        apply_runtime_config({})


def test_opponent_profile_declares_its_own_pairing():
    """The pairing an opponent byte-diffs against is the one we emit — pinned
    on a CONCLUDED pairing's profile (pending pairings live outside the repo
    per the operator's naming policy)."""
    profile = GAME_JSON_PATH.parent / "opponents" / "vm__fabi"
    apply_runtime_config({"profile": {"dir": str(profile)}})
    try:
        assert load_constitution()["agreed_between"] == ["vibecode", "vm__fabi"]
        assert config_sha256() == _sha_of(profile / "game.json")
    finally:
        apply_runtime_config({})
