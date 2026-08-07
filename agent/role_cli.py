"""Shared production CLI for the independent cop and thief processes."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import tomllib
from pathlib import Path

from agent.runtime_mode import RuntimeMode


def _parser(role: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=role, description=f"Run the {role} P2P agent")
    parser.add_argument("command", choices=("serve", "series"), nargs="?", default="serve")
    parser.add_argument("--mode", choices=[m.value for m in RuntimeMode], default="development")
    parser.add_argument("--config", default=f"{role}/config.toml")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int)
    parser.add_argument("--peer-url")
    parser.add_argument("--secret", default=os.getenv("SHARED_SECRET", ""))
    parser.add_argument("--games-dir")
    parser.add_argument("--n-gamelets", type=int, default=6)
    parser.add_argument(
        "--acceptance-fake-gmail-outbox",
        help="Explicit local-test fake; never evidence of real Gmail delivery",
    )
    return parser


def _normalise_legacy(argv: list[str]) -> list[str]:
    if argv and not argv[0].startswith("-") and argv[0] not in {"serve", "series"}:
        return ["serve", "--config", argv[0], *argv[1:]]
    return argv


def _load_private(path: str) -> dict:
    with Path(path).open("rb") as stream:
        return tomllib.load(stream)


def _detect_public_ip() -> str:
    """Return public IP: env var → ipify → empty string."""
    if ip := os.getenv("PUBLIC_IP", "").strip():
        return ip
    try:
        import urllib.request
        with urllib.request.urlopen("https://api.ipify.org", timeout=3) as resp:
            return resp.read().decode().strip()
    except Exception:
        return ""


def _model_sha(role: str, manifest_path: Path) -> str:
    if not manifest_path.exists():
        return "placeholder"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return next((item["sha256"] for item in data.get("models", []) if item["role"] == role), "")


def _model_record(role: str, manifest_path: Path) -> dict:
    if not manifest_path.exists():
        return {}
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return next((item for item in data.get("models", []) if item["role"] == role), {})


def _assert_counted_worktree_clean() -> None:
    """Bind counted Step-0 provenance to an exact committed worktree."""
    import subprocess

    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("COUNTED mode rejected: unable to verify clean git worktree") from exc
    if status.strip():
        paths = ", ".join(line[3:] for line in status.splitlines()[:5])
        raise RuntimeError(f"COUNTED mode rejected: git worktree is dirty ({paths})")


def _resolved(role: str, args: argparse.Namespace) -> tuple[dict, dict]:
    from agent.config.shared_config import config_sha256, load_shared_config

    private = _load_private(args.config)
    role_cfg = private.get(role, private.get("agent", {}))
    shared = load_shared_config()
    manifest = Path("models/MANIFEST.json")
    model = _model_record(role, manifest)
    secret = args.secret or private.get("crypto", {}).get("shared_secret", "dev-secret-change-me")
    peer_url = args.peer_url or os.getenv("PEER_URL") or role_cfg.get("peer_url", "")
    grid_size = int(shared.get("board_and_agents", {}).get("grid_size", 7))
    canonical_hash = config_sha256(shared)
    pheromones = shared.get("pheromones", {})
    scent_hash = hashlib.sha256(
        json.dumps(pheromones, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    port = args.port or int(role_cfg.get("local_port", 5000))
    public_ip = _detect_public_ip()
    advertised_host = public_ip or ("127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host)
    my_endpoint = f"http://{advertised_host}:{port}/mcp"
    runtime = {
        "role": role,
        "secret": secret,
        "config_sha256": canonical_hash,
        "opponent_url": peer_url,
        "games_dir": Path(
            args.games_dir or private.get("paths", {}).get("games_root", f"{role}/games")
        ),
        "group_name": shared.get("network_and_league", {}).get("group_name", "unknown"),
        "llm_dict": private.get("llm") or None,
        "my_endpoint": my_endpoint,
    }
    orchestrator = {
        "role": role,
        "secret": secret,
        "grid_size": grid_size,
        "model_sha256": _model_sha(role, manifest),
        "model_algorithm": model.get("algorithm", "PPO"),
        "model_schema_version": model.get("observation_schema_version", "1.0"),
        "inference_mode": model.get("inference_mode", "argmax"),
        "model_manifest_path": str(manifest),
        "team_name": shared.get("network_and_league", {}).get("group_name", ""),
        "group_id": os.getenv("GROUP_ID", ""),
        "my_endpoint": my_endpoint,
        "opponent_endpoint": peer_url,
        "config_sha256": canonical_hash,
        "canonical_config_sha256": canonical_hash,
        "scent_model_hash": scent_hash,
        "scent_numerical_vector": [
            pheromones.get("pheromone_center_intensity"),
            pheromones.get("pheromone_decay"),
            pheromones.get("pheromone_grid_size"),
        ],
        "llm_provider": private.get("llm", {}).get("provider", ""),
        "llm_model": private.get("llm", {}).get("model", ""),
        "llm_token_budget": shared.get("network_and_league", {}).get("token_budget_per_series", 0),
        "private_config": private,
        "shared_config": shared,
    }
    gmail_cfg = private.get("reports", {}).get("gmail", {})
    if args.acceptance_fake_gmail_outbox:
        from agent.gmail.sender import AcceptanceFileGmailSender

        orchestrator["gmail_sender"] = AcceptanceFileGmailSender(args.acceptance_fake_gmail_outbox)
    elif gmail_cfg.get("mode") == "send":
        from agent.gmail.sender import GmailApiSender

        orchestrator["gmail_sender"] = GmailApiSender(
            gmail_cfg.get("token_path", "secrets/gmail/token.json")
        )
    return runtime, orchestrator


async def _run(role: str, args: argparse.Namespace) -> int:
    from agent.peer_agent_runtime import PeerAgentRuntime

    mode = RuntimeMode(args.mode)
    if mode is RuntimeMode.COUNTED:
        _assert_counted_worktree_clean()
    runtime, orchestrator = _resolved(role, args)
    if args.command == "series":
        if role != "cop":
            raise ValueError("Only the cop process may initiate a series")
        from scripts.run_series import run_series

        result = await run_series(
            thief_url=runtime["opponent_url"],
            secret=runtime["secret"],
            config_sha256=runtime["config_sha256"],
            games_dir=runtime["games_dir"],
            n_gamelets=args.n_gamelets,
            group_name=runtime["group_name"],
            llm_dict=runtime["llm_dict"],
            mode=mode,
            orchestrator_config=orchestrator,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    agent = PeerAgentRuntime(**runtime, mode=mode, orchestrator_config=orchestrator)
    listen_port = args.port or int(_load_private(args.config).get(role, {}).get("local_port", 5000))
    await agent.run_async(host=args.host, port=listen_port)
    return 0


def run_role_cli(role: str, argv: list[str] | None = None) -> int:
    from agent.logging_setup import setup_dual_logging

    args = _parser(role).parse_args(_normalise_legacy(list(sys.argv[1:] if argv is None else argv)))
    setup_dual_logging(prefix=f"serve_{role}")
    return asyncio.run(_run(role, args))
