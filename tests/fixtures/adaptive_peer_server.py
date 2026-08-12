"""Adaptive peer MCP server fixture for protocol acceptance testing.

Facade over the tests/fixtures/adaptive_peer package. Keeps the original
module import path and script entry point working after the package split.

Run as a subprocess by the test_codex_real_adaptive_fixture_matrix_v11 tests.

Usage:
    python adaptive_peer_server.py --variant native --transport stdio
    python adaptive_peer_server.py --variant streamable_http --transport http --port 9001
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add cop repo root to sys.path so cop_worker imports work
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Make the sibling adaptive_peer package importable both when this file is
# executed as a script (sys.path[0] == tests/fixtures) and when imported as
# tests.fixtures.adaptive_peer_server from the repo root.
_FIXTURES_DIR = Path(__file__).resolve().parent
if str(_FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(_FIXTURES_DIR))

from adaptive_peer.builder import _build_server, main  # noqa: E402
from adaptive_peer.common import (  # noqa: E402
    _CALL_COUNTER,
    CONFORMANCE_TOOL,
    PROBE_PREFIX,
    SEMANTIC_PROOFS,
    _extract_game_id,
    _fail_response,
    _is_probe,
    _ok_response,
)

__all__ = [
    "CONFORMANCE_TOOL",
    "PROBE_PREFIX",
    "SEMANTIC_PROOFS",
    "_CALL_COUNTER",
    "_build_server",
    "_extract_game_id",
    "_fail_response",
    "_is_probe",
    "_ok_response",
    "main",
]

if __name__ == "__main__":
    main()
