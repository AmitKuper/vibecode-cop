"""Shared constants, canonical hashing, constitution access, artifact writing."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC
from pathlib import Path

from cop_worker.protocol.reference_v3 import canonical_json
from league_artifacts.ingress import STATIC_MCP, resolve_mcp_urls

REPO_ROOT = Path(__file__).resolve().parents[2]
OUR_REPOS = {
    "cop": "https://github.com/AmitKuper/vibecode-cop",
    "thief": "https://github.com/AmitKuper/vibecode-thief",
}
# Router-forwarded fallback endpoints. The DEFAULT ingress is ngrok — see
# league_artifacts.ingress for the resolution order (profile URL > live tunnel >
# static IP). Every path reaches the same local listeners; only the DECLARED
# URL changes, so play is byte-identical whichever one is used.
OUR_MCP = dict(STATIC_MCP)


def our_mcp() -> dict:
    """The MCP URLs we declare for THIS pairing (ngrok by default)."""
    try:
        from ref3_match.runtime_cfg import runtime_snapshot

        return resolve_mcp_urls(runtime_snapshot().get("network", {}))
    except Exception:
        return resolve_mcp_urls({})


# The shared constitution (rule 11): both repos load byte-identical config/game.json.
# config_sha256 is sha256(canonical(WHOLE game.json)) — a field subset would defeat the
# purpose (two teams "agreeing" while unhashed sections differ). anrbj666 pins 9ed3b2e9….
GAME_JSON_PATH = REPO_ROOT / "config" / "game.json"


def game_json_path() -> Path:
    """The constitution THIS pairing declares: the ``--config`` profile's game.json.

    ``agreed_between`` names the two groups and is inside the hash, so the file
    is per-pairing. Reading the base path unconditionally meant every series
    declared whichever pair the base file happened to name (it still said
    imreeyal/vibecode six counted games later) while the opponent profile's own
    game.json — loaded by ``--config`` and byte-diffed with the peer — never
    reached the wire (found 2026-08-18, ahk-yosi pairing). Falls back to the
    base file when no profile is selected or the profile carries no game.json.
    """
    try:
        from ref3_match.runtime_cfg import profile_dir

        selected = profile_dir()
        if selected and (selected / "game.json").is_file():
            return selected / "game.json"
    except Exception:  # no CLI profile installed (unit tests, standalone scripts)
        pass
    return GAME_JSON_PATH


def _sha(obj: object) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def load_constitution() -> dict:
    """Load the shared game.json (lazy — a missing file must not crash on import)."""
    return json.loads(game_json_path().read_text(encoding="utf-8"))


def config_sha256() -> str:
    """sha256(canonical(whole game.json)) — must equal the peer's 9ed3b2e9…."""
    return _sha(load_constitution())


def now_iso() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()


def write_artifact(obj: dict, path: Path) -> Path:
    """Write a repo artifact: pretty-printed (indent 2, insertion order) like anrbj666's."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
