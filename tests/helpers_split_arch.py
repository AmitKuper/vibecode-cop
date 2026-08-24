"""Fake worker-protocol child for the split-architecture tests (150-line rule)."""

from __future__ import annotations

from pathlib import Path

# A stand-in child that speaks the worker protocol: ready, then echoes canned replies.
_FAKE_WORKER = r"""
import json, sys
init = json.loads(sys.stdin.readline())
sys.stdout.write(json.dumps({"type": "ready", "role": init["role"]}) + "\n")
sys.stdout.flush()
for line in sys.stdin:
    cmd = json.loads(line)
    if cmd.get("type") == "shutdown":
        sys.stdout.write(json.dumps({"type": "bye"}) + "\n"); sys.stdout.flush(); break
    reply = init.get("reply") or {"type": "result", "row": {"sub_game": cmd["sub_game"]}}
    sys.stdout.write(json.dumps(reply) + "\n"); sys.stdout.flush()
"""


def _fake_launcher(tmp_path: Path) -> Path:
    path = tmp_path / "fake_worker.py"
    path.write_text(_FAKE_WORKER, encoding="utf-8")
    return path
