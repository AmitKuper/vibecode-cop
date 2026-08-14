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


def test_default_is_static_ip_even_with_a_tunnel_running(monkeypatch):
    """Static is the default, so a tunnel that happens to be up changes nothing.

    Patched rather than probing the real agent: whether ngrok is running on the
    dev box must not decide what the suite asserts.
    """
    from league_artifacts import ingress

    apply_runtime_config({})
    monkeypatch.setattr(
        ingress, "_tunnel_map", lambda *a, **k: {61224: "https://live.ngrok-free.dev"}
    )
    assert our_mcp() == OUR_MCP
    assert our_mcp()["cop"].startswith("http://62.56.220.143:61224")


def test_ngrok_is_opt_in_per_pairing(monkeypatch):
    from league_artifacts import ingress

    apply_runtime_config({"network": {"ingress": "ngrok"}})
    monkeypatch.setattr(
        ingress, "_tunnel_map", lambda *a, **k: {61224: "https://live.ngrok-free.dev"}
    )
    assert our_mcp()["cop"] == "https://live.ngrok-free.dev/mcp"
    assert our_mcp()["thief"] == OUR_MCP["thief"]  # free plan: one door only


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
