"""crewAI agents for MCP protocol discovery.

Flow (runs once at game start):
  1. MCPExplorerAgent  — probes peer_url, reads full inputSchema, and maps each
                         tool to its semantic role AND the exact parameter names.
  2. Python            — fills a deterministic template with the discovered names.
  3. SkillValidatorAgent — in mcp_skill_validator.py.
"""

from typing import Any

from crewai import Agent, Task

from agent.tools.mcp_probe_tool import probe_mcp_server

# Re-export validator for backwards compatibility
from agent.agents.mcp_skill_validator import (  # noqa: F401
    create_skill_validator_agent,
    create_skill_validator_task,
)


# ---------------------------------------------------------------------------
# Explorer agent — probes + analyses full schemas
# ---------------------------------------------------------------------------

def create_mcp_explorer_agent(llm: Any) -> Agent:
    """Agent that probes a remote MCP server and maps its full protocol."""
    return Agent(
        role="MCP Protocol Analyst",
        goal=(
            "Probe a remote MCP server with probe_mcp_server, carefully read each "
            "tool's description AND each parameter's description from inputSchema, "
            "and produce a complete protocol mapping: which tool handles each game "
            "phase, the exact parameter name for the JSON payload, HMAC signature, "
            "and game identifier, plus signing requirements and field name mapping."
        ),
        backstory=(
            "You are an API integration specialist who reverse-engineers live MCP "
            "server protocols. You always read parameter descriptions before falling "
            "back to name heuristics — a parameter named 'x' with description "
            "'HMAC-SHA256 hex digest keyed with the shared secret' is unambiguously "
            "a signature parameter regardless of its name."
        ),
        tools=[probe_mcp_server],
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )


def create_mcp_explorer_task(agent: Agent) -> Task:
    """Task: probe the peer and produce a rich protocol mapping with param names."""
    return Task(
        description=(
            "Probe the MCP server at {peer_url} using the probe_mcp_server tool.\n\n"
            "The tool returns: transport_url (auto-detected SSE endpoint), tools "
            "(each with name, description, and inputSchema including per-parameter "
            "descriptions and types), and protocol_def (if the peer exposes "
            "get_protocol()).\n\n"
            "=== HOW TO IDENTIFY PARAMETER ROLES ===\n\n"
            "Use this priority order for EVERY parameter:\n\n"
            "  1. PARAMETER DESCRIPTION (highest confidence)\n"
            "     Read tools[*].input_schema.properties[*].description.\n"
            "     These are the clearest signal — a good description explicitly "
            "states what the parameter is for. Examples of what to look for:\n"
            "       payload param  → description mentions: 'canonical JSON', 'payload', "
            "'game message', 'JSON string', 'JSON-encoded', 'sorted keys'\n"
            "       signature param → description mentions: 'HMAC', 'HMAC-SHA256', "
            "'hex digest', 'signature', 'keyed with', 'shared secret'\n"
            "       game_id param   → description mentions: 'game identifier', "
            "'game session', 'active game', 'game_id', 'session id'\n"
            "     If the description clearly identifies the role, use that parameter. Done.\n\n"
            "  2. PARAMETER NAME (medium confidence)\n"
            "     Only if description is missing or ambiguous:\n"
            "       payload param  → name contains: message, msg, payload, json, data, body\n"
            "       signature param → name contains: sig, signature, hmac, auth, token, mac\n"
            "       game_id param   → name contains: game_id, game, gid, match, session\n\n"
            "  3. PARAMETER TYPE (lowest confidence)\n"
            "     Only if both description and name are ambiguous:\n"
            "       string type → likely the payload or signature\n"
            "       (use position: first string param → payload, second → signature)\n\n"
            "Use the same priority order for TOOL roles:\n"
            "  1. TOOL DESCRIPTION — mentions 'handshake', 'initialize game', 'start' "
            "→ start tool; 'commit', 'reveal', 'turn action', 'execute action' → action tool; "
            "'health', 'ping', 'ready', 'reachable' → ping tool\n"
            "  2. TOOL NAME — contains: start/init/begin (start), "
            "action/move/commit/reveal/submit/turn (action), ping/health/status (ping)\n\n"
            "=== OUTPUT FORMAT ===\n\n"
            "Produce a JSON mapping with this structure:\n"
            '{{\n'
            '  "peer_url": "<peer_url>",\n'
            '  "transport_url": "<transport_url from probe output>",\n'
            '  "all_tools": ["<tool1>", "<tool2>", ...],\n'
            '  "signing_required": true,\n'
            '  "payload_type": "string",\n'
            '  "start_game_tool": "<exact tool name>",\n'
            '  "start_game_params": {{\n'
            '    "message_param": "<exact param name for JSON payload>",\n'
            '    "message_type": "string",\n'
            '    "signature_param": "<exact param name for HMAC, or null>"\n'
            '  }},\n'
            '  "action_tool": "<exact tool name>",\n'
            '  "action_params": {{\n'
            '    "game_id_param": "<exact param name for game identifier>",\n'
            '    "message_param": "<exact param name for JSON payload>",\n'
            '    "message_type": "string",\n'
            '    "signature_param": "<exact param name for HMAC, or null>"\n'
            '  }},\n'
            '  "ping_tool": "<exact tool name>",\n'
            '  "field_map": {{}}\n'
            "}}\n\n"
            "=== ADDITIONAL FIELDS ===\n\n"
            "  signing_required — true if ANY parameter description mentions HMAC/signature, "
            "OR any parameter name contains sig/signature/hmac/auth/mac. False otherwise.\n\n"
            "  payload_type — check the payload param's schema type: "
            "'string' → payload_type='string' (peer expects JSON-encoded string); "
            "'object' → payload_type='object' (peer expects raw JSON object); "
            "default to 'string' if unknown.\n\n"
            "  field_map — maps canonical game field names to the peer's actual field names "
            "inside the message payload. Canonical names: game_id, gamelet, step, role, "
            "phase, config_sha256, state_hash, h_commit, h_commit_ack, move, hint, intent, "
            "nonce, nonces, timestamp.\n"
            "    - If probe returned a non-null protocol_def: copy protocol_def.fields "
            "as field_map. These are the peer's own declared field names.\n"
            "    - If protocol_def is null: use {{}} (identity map, no remapping needed).\n"
        ),
        agent=agent,
        expected_output=(
            "A single JSON object with keys: peer_url, transport_url, all_tools, "
            "signing_required (bool), payload_type ('string' or 'object'), "
            "start_game_tool, start_game_params (message_param, message_type, "
            "signature_param), action_tool, action_params (game_id_param, "
            "message_param, message_type, signature_param), ping_tool, "
            "field_map (dict mapping canonical name → peer's field name, or {{}})."
        ),
    )
