"""Dynamic protocol adapter.

Discovery phase uses an LLM to map our canonical action parameters to the opponent's
MCP tool schema. Each turn the LLM is called ONCE to produce the parameter JSON, then
the tool is called directly — no crewAI agent loop overhead per turn.

crewAI is still used for the move-selection crew (orchestrator_crew.py); here we call
the LLM directly for fast single-shot parameter mapping.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from agent.mcp.client import GameMCPClient


def _extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a free-form LLM response."""
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except Exception:
            pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return None


class ProtocolAdapterCrew:
    """Adapts our game actions to the opponent's MCP protocol each turn.

    Uses one direct LLM call per action to map our canonical parameters to the
    opponent's tool schema, then calls the tool directly.  This avoids the
    multi-round-trip overhead of a full crewAI agent loop.
    """

    def __init__(
        self,
        discovered_tools: dict,
        client: "GameMCPClient",
        llm: object = None,
    ) -> None:
        self._client = client
        self._llm = llm
        # Keep only the first action-like tool schema for parameter mapping.
        self._tool_name, self._tool_schema = next(iter(discovered_tools.items()))
        props = (self._tool_schema.get("schema") or {}).get("properties", {})
        self._props_summary = (
            "\n".join(f"  {k}: {v.get('type', 'string')}" for k, v in props.items())
            if props else "(no schema available)"
        )
        logger.info(
            f"[ProtocolAdapter] Using tool '{self._tool_name}' with "
            f"{len(props)} known parameters"
        )

    def _build_mapping_prompt(self, action_description: str) -> str:
        return (
            f"Tool name: {self._tool_name}\n"
            f"Tool parameters:\n{self._props_summary}\n\n"
            f"Action to send:\n{action_description}\n\n"
            "Reply with ONLY a valid JSON object containing the mapped parameter values. "
            "No explanation, no markdown, just JSON."
        )

    async def _call_llm_once(self, prompt: str) -> str:
        """Call the LLM directly for a single mapping response."""
        # crewAI LLM wraps LiteLLM — call() accepts a list of message dicts.
        try:
            response = self._llm.call(
                messages=[
                    {"role": "system", "content": "You map game action values to JSON tool parameters. Output only valid JSON."},
                    {"role": "user", "content": prompt},
                ]
            )
            return response if isinstance(response, str) else str(response)
        except Exception as exc:
            raise RuntimeError(f"LLM call failed: {exc}") from exc

    async def execute(self, action_description: str) -> dict:
        """Map action to opponent tool parameters via one LLM call, then call the tool."""
        logger.info(f"[ProtocolAdapter] → {action_description[:120]}...")

        prompt = self._build_mapping_prompt(action_description)
        raw_response = await self._call_llm_once(prompt)
        logger.debug(f"[ProtocolAdapter] LLM raw: {raw_response!r}")

        params = _extract_json(raw_response)
        if not params:
            raise RuntimeError(
                f"LLM did not return valid JSON for tool mapping. "
                f"Raw response: {raw_response!r}"
            )

        logger.info(f"[ProtocolAdapter] calling {self._tool_name} with {list(params.keys())}")
        return await self._client._call_tool(self._tool_name, params)
