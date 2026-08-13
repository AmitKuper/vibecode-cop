"""Serving side: port preflight, role endpoints, the outbound gateway caller."""

from __future__ import annotations

import asyncio
import json as _json

from ref3_match.match_log import _wire_session_class
from ref3_match.net import _check_port, _wait_port
from ref3_match.runtime_cfg import _t


def _preflight_ports(our_cop_port: int, our_thief_port: int) -> None:
    """Port-free preflight: a stray process holding our port would silently swallow
    the peer's traffic. Refuse loudly instead — WARNINGS §5.
    """
    for _pname, _p in (("cop", our_cop_port), ("thief", our_thief_port)):
        if _check_port("127.0.0.1", _p):
            raise RuntimeError(f"port {_p} (our {_pname} endpoint) is already in use; kill it")


def _gateway_caller(client):
    """At-least-once tool caller through the central outbound gateway (pacing +
    bounded retries). Dedup-safe: turns dedupe on commit, greetings are drained,
    a re-sent audit re-carries identical records (equivocation is the refusal).
    """

    async def _call(tool: str, params: dict) -> dict:
        from cop_worker.net_gateway import GATEWAY

        r = await GATEWAY.call(
            "mcp",
            lambda: client.call_tool(tool, params),
            retries=int(_t("mcp_call_retries", 6)),
            backoff_s=0.5,
            max_backoff_s=5.0,
            label=tool,
        )
        if not r.content:
            return {"ok": getattr(r, "is_error", False) is not True}
        val = getattr(r.content[0], "text", str(r.content[0]))
        try:
            parsed = _json.loads(val)
        except (ValueError, TypeError):
            return {"ok": True, "raw": val}
        return parsed if isinstance(parsed, dict) else {"ok": True}

    return _call


async def _start_server_one(host: str, port: int, role_name: str, session=None):
    """Serve ONE reference-v3 role endpoint; returns (session, task).

    One role per OS process (rule 1); inline mode composes two in one process.
    Passing an existing ``session`` REBUILDS the HTTP stack around it (door_guard
    recovery for a wedged streamable-http layer); banked greetings survive.
    """
    from fastmcp import FastMCP

    from cop_worker.protocol.reference_v3 import register_reference_v3_tools

    if session is None:
        _Session = _wire_session_class()
        session = _Session(lambda t, p: (_ for _ in ()).throw(RuntimeError(f"no outbound ({t})")))
    app = FastMCP(name=f"vibecode-{role_name}")
    register_reference_v3_tools(app, session)
    task = asyncio.create_task(
        app.run_async(transport="http", host=host, port=port, show_banner=False)
    )
    await _wait_port("127.0.0.1", port, timeout=15.0)
    return session, task


async def _start_servers(host: str, our_cop_port: int, our_thief_port: int):
    """Serve both endpoints in THIS process (legacy inline mode).

    Returns (sessions, tasks); the caller cancels the tasks at teardown.
    """
    sessions, tasks = {}, []
    for role_name, port in (("police", our_cop_port), ("thief", our_thief_port)):
        sess, task = await _start_server_one(host, port, role_name)
        sessions[role_name] = sess
        tasks.append(task)
    return sessions, tasks


async def _dial_and_play(
    mcp_url: str,
    base_url: str,
    in_session,
    *,
    sg: int,
    our_role: str,
    terms: dict,
    opponent_group: str,
    members: list | None,
    our_counted: int,
    scent_model: str,
    move_policy: str,
    confirmed_group: str | None,
) -> dict:
    """Dial the peer's window endpoint and play one sub-game through it."""
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    from cop_worker.protocol.pipeline import discover_reference_v3
    from ref3_match.net import NoGameHappenedError
    from ref3_match.subgame import _play_subgame

    transport = StreamableHttpTransport(mcp_url)
    # Per-call cap STRICTLY below the signed response_timeout_sec (30); the SDK's
    # unset default (300s read ceiling) could breach a signed deadline (imreeyal §3.5).
    call_cap = _t("mcp_call_sec", 10.0)
    if call_cap >= float(terms.get("response_timeout_sec", 30) or 30):
        raise RuntimeError(
            f"mcp_call_sec={call_cap} must be strictly below the signed "
            f"response timeout; refusing to start"
        )
    async with Client(transport, timeout=call_cap) as client:
        # Generous probe/introspect deadlines: a tunnelled peer is slower
        # than the 5s default, which otherwise fails discovery spuriously.
        try:
            _profile, out_session = await discover_reference_v3(
                base_url,
                tool_caller=_gateway_caller(client),
                probe_timeout_s=_t("probe_sec", 30.0),
                introspect_timeout_s=_t("introspect_sec", 30.0),
            )
        except Exception as exc:
            # Discovery precedes the handshake: certainly no game yet.
            raise NoGameHappenedError(
                f"discovery failed: {type(exc).__name__}: {str(exc)[:120]}"
            ) from exc
        return await _play_subgame(
            out_session,
            in_session,
            role=our_role,
            sub_game=sg,
            group_id="vibecode",
            group_name="vibecode",
            terms=terms,
            opponent_group_hint=opponent_group,
            members=members,
            our_counted=our_counted,
            scent_model=scent_model,
            move_policy=move_policy,
            declared_opponent_group=confirmed_group,
        )
