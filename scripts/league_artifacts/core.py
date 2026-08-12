"""Shared constants, canonical hashing, constitution access, artifact writing."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC
from pathlib import Path

from cop_worker.protocol.reference_v3 import canonical_json

REPO_ROOT = Path(__file__).resolve().parents[2]
OUR_REPOS = {
    "cop": "https://github.com/AmitKuper/vibecode-cop",
    "thief": "https://github.com/AmitKuper/vibecode-thief",
}
OUR_MCP = {"cop": "http://62.56.220.143:61224/mcp", "thief": "http://62.56.220.143:61223/mcp"}

# The shared constitution (rule 11): both repos load byte-identical config/game.json.
# config_sha256 is sha256(canonical(WHOLE game.json)) — a field subset would defeat the
# purpose (two teams "agreeing" while unhashed sections differ). anrbj666 pins 9ed3b2e9….
GAME_JSON_PATH = REPO_ROOT / "config" / "game.json"


def _sha(obj: object) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def load_constitution() -> dict:
    """Load the shared game.json (lazy — a missing file must not crash on import)."""
    return json.loads(GAME_JSON_PATH.read_text(encoding="utf-8"))


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
