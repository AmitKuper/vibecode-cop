"""CLI entry point for the sparring demo."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sparring_demo import KIT_ROOT
from sparring_demo.runner import _run_all

# The original scripts/demo_vs_sparring.py docstring — kept verbatim so the
# argparse --help description is byte-identical to the pre-split script.
_DESCRIPTION = """Demo game: our cop (police) vs external sparring kit (thief) via reference-v3.

Usage:
    cd vibecode-cop
    python scripts/demo_vs_sparring.py [--kit-root PATH] [--sub-games N]

What this proves:
  - Our MCP server correctly registers the 4 reference-v3 tools
  - Sparring thief can call our tools and receive our turns
  - Our cop actively drives a full sub-game against sparring thief
  - Reference-v3 bidirectional game loop works end-to-end
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=_DESCRIPTION)
    parser.add_argument("--kit-root", type=Path, default=KIT_ROOT)
    parser.add_argument("--our-port", type=int, default=5001)
    parser.add_argument("--sparring-port", type=int, default=8931)
    parser.add_argument("--sub-games", type=int, default=1)
    args = parser.parse_args()

    kit = args.kit_root.resolve()
    if not (kit / "verify_vectors.py").is_file():
        print(f"ERROR: not a league-protocol clone: {kit}")
        return 1

    try:
        result = asyncio.run(_run_all(args.our_port, args.sparring_port, kit, args.sub_games))
        print("\n[demo] === RESULT ===")
        print(json.dumps(result, indent=2))
        passed = sum(1 for sg in result["sub_games"] if sg.get("audit_ok") is not False)
        total = result["n"]
        status = "PASS" if passed == total else f"PARTIAL ({passed}/{total})"
        print(f"[demo] STATUS: {status}")
        return 0 if passed > 0 else 1
    except Exception as exc:
        print(f"[demo] ERROR: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1
