#!/usr/bin/env python3
"""Bidirectional real-process check against an unmodified league-protocol clone."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _hidden_process_kwargs() -> dict:
    if os.name != "nt":
        return {}
    return {"creationflags": subprocess.CREATE_NO_WINDOW}


def _wait_port(host: str, port: int, process: subprocess.Popen, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited before listening (exit {process.returncode})")
        with socket.socket() as sock:
            sock.settimeout(0.2)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.1)
    raise TimeoutError(f"server did not listen on {host}:{port}")


def _stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _git(kit: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(kit), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _messages() -> tuple[dict, dict, dict, dict]:
    from agent.adaptive.reference_v3 import build_negotiation, build_turn, default_terms

    greeting = build_negotiation(
        terms=default_terms(),
        nonce="ab" * 16,
        group_id="sparring-vibecode-interop",
        group_name="Vibecode interoperability verifier",
        role="police",
        sub_game_number=1,
    )
    payload = {
        "step": 1,
        "role": "police",
        "sub_game": 1,
        "state": "grid=7x7;self=[0, 0];barriers=[]",
        "position": [0, 0],
        "move": "STAY",
        "intent": "truth",
        "hint": "I am testing interoperability",
        "verdict": "moved",
    }
    turn, record = build_turn(
        record_payload=payload,
        nonce="cd" * 16,
        sender="police",
        hint=payload["hint"],
        smell_grid={"0,0": 0.8},
    )
    audit = {"sender": "police", "records": [record], "result_claim": "timeout"}
    control = {
        "kind": "status",
        "sender": "police",
        "sub_game_number": 1,
        "status": "interop_probe",
        "step_budget": 30.0,
        "payload": {"side_effect_free": True},
    }
    return greeting, turn, audit, control


async def _our_client_to_external(url: str) -> dict:
    from agent.adaptive.pipeline import discover_reference_v3

    profile, session = await discover_reference_v3(url)
    greeting, turn, audit, control = _messages()
    responses = [
        await session.send_negotiation(greeting),
        await session.send_turn(turn, audit["records"][0]),
        await session.send_audit("police", "timeout"),
        await session.send_control(control),
    ]
    if not all(response.get("ok") for response in responses):
        raise RuntimeError(f"external server rejected a reference-v3 call: {responses}")
    return {
        "profile_hash": profile.profile_hash,
        "schema_digest": profile.schema_digest,
        "calls": 4,
        "per_turn_llm_calls": session.per_turn_llm_calls,
    }


def _external_client_to_ours(kit: Path, url: str) -> dict:
    sys.path.insert(0, str(kit))
    try:
        from sparring.transport.client import McpClient

        client = McpClient(url, timeout=10.0)
        greeting, turn, audit, control = _messages()
        try:
            responses = [
                client.negotiate(greeting),
                client.receive_turn(turn),
                client.submit_audit(audit),
                client.receive_control(control),
            ]
        finally:
            client.close()
    finally:
        sys.path.remove(str(kit))
    if not all(response.get("ok") for response in responses):
        raise RuntimeError(f"external client rejected our MCP surface: {responses}")
    return {"calls": 4, "argument_asymmetry": "submit_audit(payload)"}


def _serve_local(host: str, port: int) -> int:
    from fastmcp import FastMCP

    from agent.adaptive.reference_v3 import ReferenceV3Session, register_reference_v3_tools

    async def unavailable(_tool: str, _params: dict) -> dict:
        raise RuntimeError("outbound transport is not configured in the verifier server")

    app = FastMCP(name="vibecode-reference-v3-interop")
    register_reference_v3_tools(app, ReferenceV3Session(unavailable))
    app.run(transport="http", host=host, port=port, show_banner=False)
    return 0


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
