"""Trigger a single game via GameInitiator using public IP."""
import asyncio
import logging
from agent.game_initiator import GameInitiator
from agent.config.shared_config import load_shared_config, config_sha256 as sha256_fn

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(levelname)s: %(message)s")

PUBLIC_IP = "62.56.220.143"

async def main():
    cfg = load_shared_config()
    c_sha = sha256_fn(cfg)
    gi = GameInitiator(
        cop_url=f"http://{PUBLIC_IP}:61224/mcp",
        thief_url=f"http://{PUBLIC_IP}:61223/mcp",
        secret="dev-secret-change-me",
        config_sha256=c_sha,
    )
    print(f"config_sha256={c_sha[:12]}...")
    result = await gi.start_game()
    print("start_game result:", result)

asyncio.run(main())
