"""Ingress resolution: the static IP is the default; ngrok is opt-in per pairing.

The declared URL is what the opponent dials, so getting this wrong costs a whole
series. The free ngrok tier grants ONE static domain, so the thief's tunnel URL
changes every start — hence live resolution from the agent's API rather than a
constant.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from league_artifacts import ingress  # noqa: E402


def _fake_tunnels(monkeypatch, mapping):
    monkeypatch.setattr(ingress, "_tunnel_map", lambda *a, **k: mapping)


def test_default_mode_is_static():
    """Static is the league-facing default: two permanent doors, no agent to babysit."""
    assert ingress.DEFAULT_INGRESS == "static"
    assert ingress.resolve_mcp_urls({}, announce=None) == ingress.STATIC_MCP


def test_live_tunnels_are_declared(monkeypatch):
    _fake_tunnels(
        monkeypatch,
        {
            61224: "https://static-domain.ngrok-free.dev",
            61223: "https://random-1234.ngrok-free.app",
        },
    )
    urls = ingress.resolve_mcp_urls({"ingress": "ngrok"}, announce=None)
    assert urls == {
        "cop": "https://static-domain.ngrok-free.dev/mcp",
        "thief": "https://random-1234.ngrok-free.app/mcp",
    }


def test_missing_tunnel_falls_back_per_role(monkeypatch):
    """One tunnel up, one down: declare the tunnel for one role, static for the other."""
    _fake_tunnels(monkeypatch, {61224: "https://static-domain.ngrok-free.dev"})
    said = []
    urls = ingress.resolve_mcp_urls({"ingress": "ngrok"}, announce=said.append)
    assert urls["cop"] == "https://static-domain.ngrok-free.dev/mcp"
    assert urls["thief"] == ingress.STATIC_MCP["thief"]
    assert any("no usable tunnel for thief" in m for m in said)


def test_no_agent_running_still_returns_static(monkeypatch):
    _fake_tunnels(monkeypatch, {})
    assert ingress.resolve_mcp_urls({"ingress": "ngrok"}, announce=None) == ingress.STATIC_MCP


def test_static_mode_never_touches_the_agent(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("ngrok API must not be queried in static mode")

    monkeypatch.setattr(ingress, "_tunnel_map", _boom)
    assert ingress.resolve_mcp_urls({"ingress": "static"}, announce=None) == ingress.STATIC_MCP


def test_explicit_profile_url_wins_over_tunnel(monkeypatch):
    _fake_tunnels(monkeypatch, {61224: "https://static-domain.ngrok-free.dev"})
    urls = ingress.resolve_mcp_urls(
        {"ingress": "ngrok", "our_cop_mcp_url": "https://agreed.example/mcp"}, announce=None
    )
    assert urls["cop"] == "https://agreed.example/mcp"


def test_tunnel_map_ignores_http_duplicates_and_bad_addrs():
    payload = {
        "tunnels": [
            {"public_url": "http://plain.ngrok-free.dev", "config": {"addr": "localhost:61224"}},
            {"public_url": "https://secure.ngrok-free.dev", "config": {"addr": "localhost:61224"}},
            {"public_url": "https://weird.ngrok-free.dev", "config": {"addr": "no-port"}},
        ]
    }
    import json as _json
    from unittest.mock import patch

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return _json.dumps(payload).encode()

    with patch("urllib.request.urlopen", return_value=_Resp()):
        assert ingress._tunnel_map() == {61224: "https://secure.ngrok-free.dev"}


def test_our_mcp_uses_the_resolver(monkeypatch):
    from league_artifacts import core

    _fake_tunnels(
        monkeypatch, {61224: "https://c.ngrok-free.dev", 61223: "https://t.ngrok-free.dev"}
    )
    urls = core.our_mcp()
    assert set(urls) == {"cop", "thief"}
    assert all(u.endswith("/mcp") for u in urls.values())


def test_shared_static_domain_is_refused_not_guessed():
    """Free tier injects one domain into both tunnels; only the last registration
    routes. Declaring it for both roles would send cop traffic to the thief door,
    so an ambiguous URL is dropped rather than guessed (observed live 2026-08-14).
    """
    collided = {
        61224: "https://one-domain.ngrok-free.dev",
        61223: "https://one-domain.ngrok-free.dev",
    }
    assert ingress._drop_collisions(collided) == {}
    unique = {61224: "https://a.ngrok-free.dev", 61223: "https://b.ngrok-free.app"}
    assert ingress._drop_collisions(unique) == unique
