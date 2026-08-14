"""Which public URLs we DECLARE for our two MCP doors.

Two ingress paths reach the SAME local listeners (61224 cop / 61223 thief):

* ``ngrok``  — the default. Public HTTPS via the ngrok agent. The cop rides the
  account's free static domain; the thief gets an EPHEMERAL URL each start
  (free tier grants one static domain), so tunnel URLs are resolved LIVE from
  the agent's local API rather than hardcoded.
* ``static`` — the router-forwarded public IP. No tunnel needed.

Resolution order, per role: an explicit profile ``our_<role>_mcp_url`` always
wins; then the live tunnel when ingress is ngrok; then the static IP. A missing
ngrok agent never breaks a match — it falls back to static and says so.
"""

from __future__ import annotations

import json
import urllib.request

#: Router-forwarded public endpoints (no tunnel).
STATIC_MCP = {
    "cop": "http://62.56.220.143:61224/mcp",
    "thief": "http://62.56.220.143:61223/mcp",
}
LOCAL_PORTS = {"cop": 61224, "thief": 61223}
NGROK_API = "http://127.0.0.1:4040/api/tunnels"
DEFAULT_INGRESS = "ngrok"


def _tunnel_map(api_url: str = NGROK_API, timeout: float = 2.0) -> dict:
    """{local_port: public_https_url} from the running ngrok agent; {} if absent."""
    try:
        with urllib.request.urlopen(api_url, timeout=timeout) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}
    found: dict[int, str] = {}
    for tun in payload.get("tunnels", []) or []:
        public = str(tun.get("public_url") or "")
        addr = str((tun.get("config") or {}).get("addr") or "")
        if not public.startswith("https://") or ":" not in addr:
            continue  # http duplicates and malformed entries are not usable
        try:
            port = int(addr.rsplit(":", 1)[1])
        except ValueError:
            continue
        found.setdefault(port, public)  # first https wins; ngrok lists https first
    return _drop_collisions(found)


def _drop_collisions(found: dict) -> dict:
    """Discard any URL claimed by more than one local port.

    The free tier grants ONE static domain and INJECTS it into every tunnel that
    does not name its own URL, so two tunnels can advertise the same hostname
    while only the last registration actually routes (observed 2026-08-14).
    Declaring that URL for both roles would send the opponent's cop traffic to
    our thief door. Ambiguous is worse than absent: drop it and fall back.
    """
    seen: dict[str, int] = {}
    for port, url in found.items():
        seen[url] = seen.get(url, 0) + 1
    return {p: u for p, u in found.items() if seen[u] == 1}


def resolve_mcp_urls(net: dict | None = None, *, announce=print) -> dict:
    """Declared {"cop": url, "thief": url} for this pairing.

    ``net`` is the profile's [network] table. Explicit URLs win, then ngrok
    (when selected), then static. Never raises: a game must start even with no
    tunnel running.
    """
    net = net or {}
    mode = str(net.get("ingress") or DEFAULT_INGRESS).strip().lower()
    tunnels = _tunnel_map() if mode == "ngrok" else {}
    urls, sources = {}, {}
    for role in ("cop", "thief"):
        explicit = net.get(f"our_{role}_mcp_url")
        if explicit:
            urls[role], sources[role] = str(explicit), "profile"
            continue
        tunnel = tunnels.get(LOCAL_PORTS[role])
        if tunnel:
            urls[role], sources[role] = f"{tunnel.rstrip('/')}/mcp", "ngrok"
        else:
            urls[role], sources[role] = STATIC_MCP[role], "static"
    if mode == "ngrok" and announce:
        missing = [r for r in ("cop", "thief") if sources[r] == "static"]
        if missing:
            announce(
                f"[ingress] ngrok requested but no usable tunnel for {', '.join(missing)} "
                f"- declaring the static IP for those roles. Start one with "
                f"`ngrok start cop` (free tier: run ONE tunnel; two share the single "
                f"static domain and only the last one routes)."
            )
        for role in ("cop", "thief"):
            if sources[role] == "ngrok":
                announce(f"[ingress] {role} declared via ngrok: {urls[role]}")
    return urls
