"""Entry point for running Cop process: python -m cop."""

import asyncio
import logging
import os
import sys
import tomllib
from pathlib import Path

from agent.peer_agent_runtime import PeerAgentRuntime

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
)

logger = logging.getLogger(__name__)


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Load key=value pairs from .env into os.environ (existing vars win)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


async def main() -> int:
    """Load config, initialise PeerAgentRuntime (MCP server + PeerRuntime), run server."""
    _load_dotenv()

    # Accept config path as CLI arg; fall back to role-specific then root config.toml
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
    elif Path("cop/config.toml").exists():
        config_path = Path("cop/config.toml")
    else:
        config_path = Path("config.toml")

    try:
        with open(config_path, "rb") as f:
            config = tomllib.load(f)

        # Support both [cop] and generic [agent] sections
        agent_cfg = config.get("cop", config.get("agent", {}))
        role = agent_cfg.get("role", "cop")
        local_port = int(os.environ.get("LOCAL_PORT", agent_cfg.get("local_port", 5000)))
        peer_url = os.environ.get("PEER_URL", agent_cfg.get("peer_url", ""))

        shared_secret = os.environ.get(
            "SHARED_SECRET",
            config.get("crypto", {}).get("shared_secret", "dev-secret-change-me"),
        )

        from agent.config.shared_config import config_sha256 as _sha256_fn
        from agent.config.shared_config import load_shared_config

        game_cfg = load_shared_config()
        config_sha256 = _sha256_fn(game_cfg)
        group_name = game_cfg.get("network_and_league", {}).get("group_name", "unknown")

        games_dir = Path(config.get("paths", {}).get("games_root", "cop/games"))
        llm_config = config.get("llm", {})

        # Production runtime: PeerAgentRuntime = MCP server + PeerRuntime
        runtime = PeerAgentRuntime(
            role=role,
            secret=shared_secret,
            config_sha256=config_sha256,
            opponent_url=peer_url,
            games_dir=games_dir,
            group_name=group_name,
            llm_dict=llm_config if llm_config else None,
        )

        logger.info(f"Starting Cop PeerAgentRuntime on port {local_port} (binding 0.0.0.0)")
        await runtime.run_async(host="0.0.0.0", port=local_port)
        return 0

    except Exception as e:
        logger.error(f"PeerAgentRuntime failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
