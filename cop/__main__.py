"""Entry point for running Cop process: python -m cop."""

import asyncio
import logging
import os
import sys
import tomllib
from pathlib import Path

from agent.orchestrator import GameOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
)

logger = logging.getLogger(__name__)


async def main() -> int:
    """Load config, initialize GameOrchestrator, run MCP server."""
    config_path = Path("cop/config.toml")
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])

    try:
        # Load config
        with open(config_path, "rb") as f:
            config = tomllib.load(f)

        role = config["cop"]["role"]
        local_port = int(os.environ.get("LOCAL_PORT", config["cop"]["local_port"]))
        peer_url = config["cop"]["peer_url"]

        # TODO: Load shared_secret from secure config or environment
        # For now, use a placeholder (MUST be configured in production)
        shared_secret = config.get("crypto", {}).get("shared_secret", "dev-secret-change-me")

        # Compute SHA-256 from the shared canonical game config
        from agent.config.shared_config import load_shared_config, config_sha256 as _sha256_fn
        game_cfg = load_shared_config()
        config_sha256 = _sha256_fn(game_cfg)
        group_name = game_cfg.get("network_and_league", {}).get("group_name", "unknown")

        games_dir = Path(config.get("paths", {}).get("games_root", "cop/games"))

        # Load LLM config
        llm_config = config.get("llm", {})

        # Create GameOrchestrator
        orchestrator = GameOrchestrator(
            role=role,
            secret=shared_secret,
            config_sha256=config_sha256,
            games_dir=games_dir,
            opponent_url=peer_url,
            local_url=f"http://localhost:{local_port}",
            llm_dict=llm_config if llm_config else None,
            group_name=group_name,
        )

        logger.info(f"Starting Cop agent on port {local_port}")
        await orchestrator.run_async(host="localhost", port=local_port)
        return 0

    except Exception as e:
        logger.error(f"Orchestrator failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
