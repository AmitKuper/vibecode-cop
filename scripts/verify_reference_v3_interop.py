#!/usr/bin/env python3
"""Bidirectional real-process check against an unmodified league-protocol clone.

This file is the entry point and public FACADE; the implementation lives in the
``ref3_interop`` package (process helpers + wire calls, <=150 lines per module).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from ref3_interop.procs import _git, _hidden_process_kwargs, _stop, _wait_port
from ref3_interop.wire import (
    _external_client_to_ours,
    _messages,
    _our_client_to_external,
    _serve_local,
)

__all__ = [
    "_external_client_to_ours",
    "_git",
    "_hidden_process_kwargs",
    "_messages",
    "_our_client_to_external",
    "_serve_local",
    "_stop",
    "_wait_port",
    "main",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit-root", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--external-port", type=int, default=8871)
    parser.add_argument("--local-port", type=int, default=8872)
    parser.add_argument("--serve-local", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve_local:
        return _serve_local(args.host, args.local_port)
    if args.kit_root is None:
        parser.error("--kit-root is required")

    kit = args.kit_root.resolve()
    if not (kit / "verify_vectors.py").is_file():
        raise FileNotFoundError(f"not a league-protocol clone: {kit}")
    sha = _git(kit, "rev-parse", "HEAD")
    status_before = _git(kit, "status", "--short")
    if status_before:
        raise RuntimeError("external protocol clone must be clean before verification")
    vector_run = subprocess.run(
        [sys.executable, "verify_vectors.py"],
        cwd=kit,
        check=True,
        capture_output=True,
        text=True,
    )
    if "ALL VECTORS PASS" not in vector_run.stdout:
        raise RuntimeError("external protocol vectors did not report ALL VECTORS PASS")

    external_process = local_process = None
    try:
        with tempfile.TemporaryDirectory(prefix="reference_v3_interop_") as artifacts:
            external_process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "sparring.cli",
                    "serve",
                    "--group-id",
                    "sparring-external-kit",
                    "--host",
                    args.host,
                    "--port",
                    str(args.external_port),
                    "--artifacts",
                    artifacts,
                ],
                cwd=kit,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **_hidden_process_kwargs(),
            )
            _wait_port(args.host, args.external_port, external_process)
            outbound = asyncio.run(
                _our_client_to_external(f"http://{args.host}:{args.external_port}")
            )

            local_process = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--serve-local",
                    "--host",
                    args.host,
                    "--local-port",
                    str(args.local_port),
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **_hidden_process_kwargs(),
            )
            _wait_port(args.host, args.local_port, local_process)
            inbound = _external_client_to_ours(kit, f"http://{args.host}:{args.local_port}/mcp")
    finally:
        _stop(local_process)
        _stop(external_process)

    status_after = _git(kit, "status", "--short")
    if status_after:
        raise RuntimeError("external protocol clone changed during verification")
    print(
        json.dumps(
            {
                "status": "PASS",
                "external_sha": sha,
                "external_tree_clean": True,
                "external_vectors": "PASS",
                "our_client_to_external_server": outbound,
                "external_client_to_our_server": inbound,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
