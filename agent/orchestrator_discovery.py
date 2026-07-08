"""Protocol discovery mixin — runs once at game start.

Flow:
  1. Python probes the peer's MCP server:
       - Auto-detects SSE transport URL (tries /sse, /mcp/sse, /v1/sse, /)
       - Retrieves full inputSchema for every tool
       - Calls get_protocol() if the peer exposes it → yields protocol_def with
         field name mapping, signing scheme, and payload encoding
  2. MCPExplorerAgent (crewAI + LLM) analyses probe output and produces a
     protocol mapping:
       - Which tool handles start_game / action / ping
       - Exact MCP parameter names for payload, HMAC signature, and game_id
       - Whether the peer expects HMAC signing (signing_required)
       - Whether the payload param is a JSON string or raw object (payload_type)
       - field_map: canonical concept name → peer's actual field name inside payload
  3. Python fills a deterministic template with those discovered values and
     writes agent/skills/game_<id>_mcp.py. The skill includes a FIELD_MAP
     constant and _remap() helper that translates our internal field names to
     whatever the peer uses before serialising and signing.
  4. SkillValidatorAgent reviews the file; on failure Python regenerates it.
  5. The skill module is imported; self.mcp_skill is set for the game.
  6. The skill file is deleted at game end (call cleanup_skill).

When no LLM is configured or the explorer fails, all values are derived from
inputSchema via keyword heuristics and from protocol_def (if available) —
still no hardcoded names.
"""

import importlib
import importlib.util
import json
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path(__file__).parent / "skills"
_SECRET_PLACEHOLDER = "__SECRET__"
_MAX_VALIDATION_ATTEMPTS = 3

# Canonical concept names we use internally in msg_dict
_CANONICAL_FIELDS = [
    "game_id", "gamelet", "step", "role", "phase", "config_sha256",
    "state_hash", "h_commit", "h_commit_ack", "move", "hint", "intent",
    "nonce", "nonces", "timestamp",
]


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _skill_module_name(game_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", game_id)
    return f"agent.skills.game_{safe}_mcp"


def _skill_path(game_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", game_id)
    return _SKILLS_DIR / f"game_{safe}_mcp.py"


# ---------------------------------------------------------------------------
# Skill file generation — deterministic Python, no LLM
# ---------------------------------------------------------------------------

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
    # Determine whether any remapping is actually needed
    effective_map = {k: v for k, v in (field_map or {}).items() if k != v}
    needs_remap = bool(effective_map)

    # Build FIELD_MAP source and _remap() function
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

    # Payload serialisation expression
    payload_expr = f"canonical_json({payload_var})" if payload_as_string else payload_var

    # Build inline MCP param dicts as source-code strings
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


def _write_skill_from_mapping(
    skill_path: Path, transport_url: str, mapping: dict
) -> None:
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
        f"ping={mapping.get('ping_tool', 'ping')}, "
        f"signing={signing_required}, payload_type={mapping.get('payload_type', 'string')}, "
        f"transport={transport_url}, "
        f"remapped_fields={list(effective_remap) or 'none'})"
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
        return next(
            (n for n in tool_names if any(h in n.lower() for h in hints)), default
        )

    start_tool  = _tool(["start", "init", "begin", "new"], "start_game")
    action_tool = _tool(["action", "move", "commit", "reveal", "submit", "turn"], "action")
    ping_tool   = _tool(["ping", "health", "status", "alive", "check"], "ping")

    def _param_props(tool_name: str) -> dict:
        return (
            probe_schemas.get(tool_name, {})
            .get("input_schema", {})
            .get("properties", {})
        )

    def _find(props: dict, hints: list[str], default: str) -> str:
        return next(
            (p for p in props if any(h in p.lower() for h in hints)), default
        )

    def _param_type(props: dict, param: str) -> str:
        return props.get(param, {}).get("type", "string")

    sp = _param_props(start_tool)
    ap = _param_props(action_tool)

    start_msg_name = _find(sp, ["message", "msg", "payload", "json", "data", "body"], "message_json")
    act_msg_name   = _find(ap, ["message", "msg", "payload", "json", "data", "body"], "message_json")

    start_sig_name = _find(sp, ["sig", "signature", "hmac", "auth", "token", "mac"], "")
    act_sig_name   = _find(ap, ["sig", "signature", "hmac", "auth", "token", "mac"], "")
    signing_required = bool(start_sig_name or act_sig_name)

    payload_as_string = _param_type(sp, start_msg_name) != "object"

    # field_map from protocol_def if available; else identity
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
        f"transport={transport_url}, "
        f"remapped_fields={list(effective_remap) or 'none'})"
    )


def _parse_explorer_mapping(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        return json.loads(m.group())
    raise ValueError("No valid JSON object found in explorer output")


# ---------------------------------------------------------------------------
# Discovery mixin
# ---------------------------------------------------------------------------

class DiscoveryMixin:
    """Mixin: fully-agentic MCP protocol discovery."""

    role: str
    llm: object
    secret: str
    protocol_model: dict
    mcp_skill: object

    def discover_protocol(self, game_id: str, peer_url: str) -> None:
        """Probe peer, understand its schema, write and import a skill adapter."""
        logger.info(f"[{self.role}] Starting MCP discovery for game {game_id} at {peer_url}")

        transport_url, probe_schemas, protocol_def = self._probe_full(peer_url)
        explorer_raw = self._run_explorer_crew(peer_url)

        skill_path = _skill_path(game_id)
        self._write_skill(skill_path, transport_url, probe_schemas, explorer_raw, protocol_def)

        skill_path = self._validate_and_fix_loop(
            game_id, skill_path, transport_url, probe_schemas, explorer_raw, protocol_def
        )

        skill_module = self._load_skill(game_id, skill_path)
        self.mcp_skill = skill_module
        self.protocol_model = {
            "discovered": True,
            "peer_url": peer_url,
            "transport_url": transport_url,
            "skill_path": str(skill_path),
            "tools": list(probe_schemas.keys()),
            "explorer_mapping": explorer_raw,
            "protocol_def": protocol_def,
        }
        logger.info(f"[{self.role}] Discovery done. Skill loaded from {skill_path}.")

    # ------------------------------------------------------------------
    # Step 1 — probe
    # ------------------------------------------------------------------

    def _probe_full(self, peer_url: str) -> tuple[str, dict, dict | None]:
        """Probe peer; auto-detect transport. Returns (transport_url, schemas, protocol_def)."""
        from agent.tools.mcp_probe_tool import _probe_sync
        base = peer_url.rstrip("/")
        transport_url, result, protocol_def = _probe_sync(base)
        has_proto = protocol_def is not None
        logger.info(
            f"[{self.role}] Probed {base}: transport={transport_url}, "
            f"tools={list(result)}, protocol_def={'yes' if has_proto else 'no'}"
        )
        return transport_url, result, protocol_def

    # ------------------------------------------------------------------
    # Step 2 — explorer crew
    # ------------------------------------------------------------------

    def _run_explorer_crew(self, peer_url: str) -> str:
        if self.llm is None:
            return ""
        try:
            from crewai import Crew
            from agent.agents.mcp_explorer_agent import (
                create_mcp_explorer_agent,
                create_mcp_explorer_task,
            )
            explorer = create_mcp_explorer_agent(llm=self.llm)
            e_task = create_mcp_explorer_task(explorer)
            crew = Crew(agents=[explorer], tasks=[e_task], verbose=False)
            result = crew.kickoff(inputs={"peer_url": peer_url})
            raw = result.raw if hasattr(result, "raw") else str(result)
            logger.info(f"[{self.role}] Explorer output: {raw[:300]}")
            return raw
        except Exception as exc:
            logger.warning(f"[{self.role}] Explorer crew failed ({exc}); using schema heuristics.")
            return ""

    # ------------------------------------------------------------------
    # Step 3 — write skill
    # ------------------------------------------------------------------

    def _write_skill(
        self,
        skill_path: Path,
        transport_url: str,
        probe_schemas: dict,
        explorer_raw: str,
        protocol_def: dict | None,
    ) -> None:
        if explorer_raw:
            try:
                mapping = _parse_explorer_mapping(explorer_raw)
                eff_transport = mapping.get("transport_url") or transport_url
                # If explorer didn't return field_map but we have protocol_def, use it
                if not mapping.get("field_map") and protocol_def:
                    mapping["field_map"] = protocol_def.get("fields", {})
                _write_skill_from_mapping(skill_path, eff_transport, mapping)
                return
            except Exception as exc:
                logger.warning(
                    f"[{self.role}] Could not use explorer mapping ({exc}); "
                    "falling back to schema heuristics."
                )
        _write_skill_from_schemas(skill_path, transport_url, probe_schemas, protocol_def)

    # ------------------------------------------------------------------
    # Step 4 — validate + fix loop
    # ------------------------------------------------------------------

    def _validate_and_fix_loop(
        self,
        game_id: str,
        skill_path: Path,
        transport_url: str,
        probe_schemas: dict,
        explorer_raw: str,
        protocol_def: dict | None,
    ) -> Path:
        for attempt in range(1, _MAX_VALIDATION_ATTEMPTS + 1):
            try:
                verdict, issues = self._run_validator_crew(skill_path)
            except Exception as exc:
                logger.warning(f"[{self.role}] Validator error on attempt {attempt}: {exc}")
                break

            if verdict:
                logger.info(f"[{self.role}] Skill validation PASSED on attempt {attempt}.")
                break

            logger.warning(
                f"[{self.role}] Skill validation FAILED on attempt {attempt}: {issues}. "
                "Regenerating…"
            )
            self._write_skill(skill_path, transport_url, probe_schemas, explorer_raw, protocol_def)
        else:
            logger.error(
                f"[{self.role}] Skill still invalid after {_MAX_VALIDATION_ATTEMPTS} attempts."
            )
        return skill_path

    def _run_validator_crew(self, skill_path: Path) -> tuple[bool, list[str]]:
        from crewai import Crew
        from agent.agents.mcp_explorer_agent import (
            create_skill_validator_agent,
            create_skill_validator_task,
        )
        validator = create_skill_validator_agent(llm=self.llm)
        v_task = create_skill_validator_task(validator)
        crew = Crew(agents=[validator], tasks=[v_task], verbose=False)
        result = crew.kickoff(inputs={"skill_path": str(skill_path)})
        raw = result.raw if hasattr(result, "raw") else str(result)
        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group())
                valid = bool(data.get("valid", False))
                issues = data.get("issues", [])
                logger.info(f"[{self.role}] Validator verdict: {data.get('verdict', raw[:80])}")
                return valid, issues
        except Exception as exc:
            logger.debug(f"[{self.role}] Could not parse validator JSON: {exc}")
        return self._python_validate_skill(skill_path)

    def _python_validate_skill(self, skill_path: Path) -> tuple[bool, list[str]]:
        import ast
        issues: list[str] = []
        try:
            source = skill_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except SyntaxError as exc:
            return False, [f"SyntaxError: {exc}"]
        except FileNotFoundError:
            return False, ["File not found"]
        names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
        }
        for required in ("start_game", "action", "ping"):
            if required not in names:
                issues.append(f"Missing function: {required}")
        return len(issues) == 0, issues

    # ------------------------------------------------------------------
    # Step 5 — load
    # ------------------------------------------------------------------

    def _load_skill(self, game_id: str, skill_path: Path) -> object:
        code = skill_path.read_text(encoding="utf-8")
        code = code.replace(_SECRET_PLACEHOLDER, self.secret)
        skill_path.write_text(code, encoding="utf-8")
        mod_name = _skill_module_name(game_id)
        sys.modules.pop(mod_name, None)
        spec = importlib.util.spec_from_file_location(mod_name, skill_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        logger.info(f"[{self.role}] Imported skill module {mod_name}")
        return module

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup_skill(self, game_id: str) -> None:
        path = _skill_path(game_id)
        mod_name = _skill_module_name(game_id)
        sys.modules.pop(mod_name, None)
        if path.exists():
            path.unlink()
            logger.info(f"[{self.role}] Deleted ephemeral skill {path}")
        self.mcp_skill = None

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self.protocol_model.get("available_tools", [])
