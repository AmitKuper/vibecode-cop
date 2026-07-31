"""Skill file rendering — constants, path helpers, _render_skill."""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path(__file__).parent / "skills"
_SECRET_PLACEHOLDER = "__SECRET__"
_MAX_VALIDATION_ATTEMPTS = 3

_CANONICAL_FIELDS = [
    "game_id", "gamelet", "step", "role", "phase", "config_sha256",
    "state_hash", "h_commit", "h_commit_ack", "move", "hint", "intent",
    "nonce", "nonces", "timestamp",
]


def _skill_module_name(game_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", game_id)
    return f"agent.skills.game_{safe}_mcp"


def _skill_path(game_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", game_id)
    return _SKILLS_DIR / f"game_{safe}_mcp.py"


def _render_skill(
    transport_url: str,
    start_tool: str,
    start_msg: str,
    start_sig: str | None,
    action_tool: str,
    act_gid: str,
    act_msg: str,
    act_sig: str | None,
    ping_tool: str,
    payload_as_string: bool = True,
    field_map: dict | None = None,
) -> str:
    """Generate the ephemeral skill Python file.

    field_map maps our canonical field names → peer's actual field names.
    An empty or identity map means no renaming is needed.
    """
    effective_map = {k: v for k, v in (field_map or {}).items() if k != v}
    needs_remap = bool(effective_map)

    if needs_remap:
        full_map = {k: (field_map or {}).get(k, k) for k in _CANONICAL_FIELDS}
        field_map_src = f"FIELD_MAP = {full_map!r}"
        remap_src = (
            "def _remap(msg: dict) -> dict:\n"
            "    return {FIELD_MAP.get(k, k): v for k, v in msg.items()}"
        )
        payload_var = "_remap(msg_dict)"
    else:
        field_map_src = "FIELD_MAP = {}  # identity — no field renaming needed"
        remap_src = (
            "def _remap(msg: dict) -> dict:\n"
            "    return msg"
        )
        payload_var = "msg_dict"

    payload_expr = f"canonical_json({payload_var})" if payload_as_string else payload_var

    start_params = f"        {start_msg!r}: {payload_expr}"
    if start_sig:
        start_params += f",\n        {start_sig!r}: sign_message({payload_var}, SECRET)"

    act_params = (
        f"        {act_gid!r}: game_id,\n"
        f"        {act_msg!r}: {payload_expr}"
    )
    if act_sig:
        act_params += f",\n        {act_sig!r}: sign_message({payload_var}, SECRET)"

    needs_crypto = payload_as_string or bool(start_sig or act_sig)
    crypto_import = (
        "from agent.mcp.crypto import canonical_json, sign_message"
        if needs_crypto else ""
    )

    return f'''"""Auto-generated MCP skill — ephemeral, deleted at game end."""
import asyncio
import json
import logging

from fastmcp import Client
from fastmcp.client.transports import SSETransport
{crypto_import}

TRANSPORT_URL = {transport_url!r}
SECRET        = {_SECRET_PLACEHOLDER!r}
logger        = logging.getLogger(__name__)

{field_map_src}


{remap_src}


async def _call(tool: str, params: dict) -> dict:
    transport = SSETransport(TRANSPORT_URL)
    async with Client(transport) as c:
        r = await c.call_tool(tool, params)
        if r.content:
            item = r.content[0]
            text = item.text if hasattr(item, "text") else str(item)
            try:
                return json.loads(text)
            except Exception:
                return {{"ok": True, "raw": text}}
        return {{"ok": True}}


async def start_game(msg_dict: dict) -> dict:
    return await _call({start_tool!r}, {{
{start_params},
    }})


async def action(game_id: str, msg_dict: dict) -> dict:
    return await _call({action_tool!r}, {{
{act_params},
    }})


async def ping() -> dict:
    return await _call({ping_tool!r}, {{}})
'''
