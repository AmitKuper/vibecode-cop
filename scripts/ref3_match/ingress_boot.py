"""Bring our public ingress up before a match declares its URLs."""

from __future__ import annotations


def ensure_ingress(announce=print) -> None:
    """Start the ngrok tunnel when ngrok is the selected ingress.

    Never fatal: with no agent, no ngrok binary, an explicit profile URL, or
    `ingress = "static"`, we simply declare the router-forwarded IP instead.
    """
    try:
        from league_artifacts.ngrok_agent import ensure_tunnel

        from ref3_match.runtime_cfg import runtime_snapshot

        net = runtime_snapshot().get("network", {})
        if str(net.get("ingress") or "ngrok").lower() != "ngrok":
            return
        if net.get("our_cop_mcp_url"):
            return  # the pairing declares an explicit URL; nothing to start
        ensure_tunnel(announce=announce)
    except Exception as exc:  # ingress must never block a match
        if announce:
            announce(f"[ingress] autostart skipped ({type(exc).__name__})")
