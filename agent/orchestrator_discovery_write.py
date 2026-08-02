"""Skill file writing helpers for discovery."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from agent.orchestrator_discovery_render import _SKILLS_DIR, _render_skill

logger = logging.getLogger(__name__)


def _parse_explorer_mapping(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        return json.loads(m.group())
    raise ValueError("No valid JSON object found in explorer output")


def _write_skill_from_mapping(skill_path: Path, transport_url: str, mapping: dict) -> None:
    sp = mapping.get("start_game_params", {})
    ap = mapping.get("action_params", {})
    signing_required = mapping.get("signing_required", True)
    payload_as_string = mapping.get("payload_type", "string") == "string"
    field_map = mapping.get("field_map") or {}
    start_sig = sp.get("signature_param") if signing_required else None
    act_sig = ap.get("signature_param") if signing_required else None
    code = _render_skill(
        transport_url=transport_url,
        start_tool=mapping["start_game_tool"],
        start_msg=sp.get("message_param", "message_json"),
        start_sig=start_sig if start_sig else None,
        action_tool=mapping["action_tool"],
        act_gid=ap.get("game_id_param", "game_id"),
        act_msg=ap.get("message_param", "message_json"),
        act_sig=act_sig if act_sig else None,
        ping_tool=mapping.get("ping_tool", "ping"),
        payload_as_string=payload_as_string,
        field_map=field_map,
    )
    _SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(code, encoding="utf-8")
    effective_remap = {k: v for k, v in field_map.items() if k != v}
    logger.info(
        f"Skill written from explorer mapping → {skill_path.name} "
        f"(start={mapping['start_game_tool']}, action={mapping['action_tool']}, "
        f"ping={mapping.get('ping_tool', 'ping')}, signing={signing_required}, "
        f"payload_type={mapping.get('payload_type', 'string')}, "
        f"transport={transport_url}, remapped_fields={list(effective_remap) or 'none'})"
    )


def _write_skill_from_schemas(
    skill_path: Path,
    transport_url: str,
    probe_schemas: dict,
    protocol_def: dict | None = None,
) -> None:
    """Derive all values from inputSchema + protocol_def via keyword heuristics."""
    tool_names = list(probe_schemas.keys())

    def _tool(hints: list[str], default: str) -> str:
        return next((n for n in tool_names if any(h in n.lower() for h in hints)), default)

    start_tool = _tool(["start", "init", "begin", "new"], "start_game")
    action_tool = _tool(["action", "move", "commit", "reveal", "submit", "turn"], "action")
    ping_tool = _tool(["ping", "health", "status", "alive", "check"], "ping")

    def _param_props(tool_name: str) -> dict:
        return probe_schemas.get(tool_name, {}).get("input_schema", {}).get("properties", {})

    def _find(props: dict, hints: list[str], default: str) -> str:
        return next((p for p in props if any(h in p.lower() for h in hints)), default)

    def _param_type(props: dict, param: str) -> str:
        return props.get(param, {}).get("type", "string")

    sp = _param_props(start_tool)
    ap = _param_props(action_tool)
    _msg_keys = ["message", "msg", "payload", "json", "data", "body"]
    start_msg_name = _find(sp, _msg_keys, "message_json")
    act_msg_name = _find(ap, _msg_keys, "message_json")
    start_sig_name = _find(sp, ["sig", "signature", "hmac", "auth", "token", "mac"], "")
    act_sig_name = _find(ap, ["sig", "signature", "hmac", "auth", "token", "mac"], "")
    signing_required = bool(start_sig_name or act_sig_name)
    payload_as_string = _param_type(sp, start_msg_name) != "object"
    field_map = (protocol_def or {}).get("fields", {})

    code = _render_skill(
        transport_url=transport_url,
        start_tool=start_tool,
        start_msg=start_msg_name,
        start_sig=start_sig_name or None,
        action_tool=action_tool,
        act_gid=_find(ap, ["game_id", "game", "gid", "match", "id"], "game_id"),
        act_msg=act_msg_name,
        act_sig=act_sig_name or None,
        ping_tool=ping_tool,
        payload_as_string=payload_as_string,
        field_map=field_map,
    )
    _SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(code, encoding="utf-8")
    effective_remap = {k: v for k, v in field_map.items() if k != v}
    logger.info(
        f"Skill written from schema heuristics → {skill_path.name} "
        f"(signing={signing_required}, payload_as_string={payload_as_string}, "
        f"transport={transport_url}, remapped_fields={list(effective_remap) or 'none'})"
    )
