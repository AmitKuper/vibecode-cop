"""Pin the profile-driven declared MCP URLs: a pairing may declare tunnel URLs
via [network] our_cop_mcp_url / our_thief_mcp_url; without an override the
static-IP defaults hold, byte-identical to every previously filed declaration.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from league_artifacts.core import OUR_MCP, our_mcp  # noqa: E402
from ref3_match.runtime_cfg import apply_runtime_config  # noqa: E402


def test_default_is_static_ip():
    apply_runtime_config({})
    assert our_mcp() == OUR_MCP
    assert our_mcp()["cop"].startswith("http://62.56.220.143:61224")


def test_profile_override_declares_tunnel_urls():
    apply_runtime_config(
        {
            "network": {
                "our_cop_mcp_url": "https://wilt-habitant-reopen.ngrok-free.dev/mcp",
                "our_thief_mcp_url": "https://thief-ephemeral.ngrok-free.app/mcp",
            }
        }
    )
    try:
        urls = our_mcp()
        assert urls["cop"] == "https://wilt-habitant-reopen.ngrok-free.dev/mcp"
        assert urls["thief"] == "https://thief-ephemeral.ngrok-free.app/mcp"
    finally:
        apply_runtime_config({})


def test_partial_override_keeps_static_for_the_other_role():
    apply_runtime_config(
        {"network": {"our_cop_mcp_url": "https://wilt-habitant-reopen.ngrok-free.dev/mcp"}}
    )
    try:
        urls = our_mcp()
        assert urls["cop"].endswith("ngrok-free.dev/mcp")
        assert urls["thief"] == OUR_MCP["thief"]
    finally:
        apply_runtime_config({})
