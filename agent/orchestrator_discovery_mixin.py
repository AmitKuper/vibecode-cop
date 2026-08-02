"""DiscoveryMixin — agentic MCP protocol discovery."""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path

from agent.orchestrator_discovery_render import _SECRET_PLACEHOLDER, _skill_module_name, _skill_path
from agent.orchestrator_discovery_validate import validate_skill_loop
from agent.orchestrator_discovery_write import (
    _parse_explorer_mapping,
    _write_skill_from_mapping,
    _write_skill_from_schemas,
)

logger = logging.getLogger(__name__)


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
        skill_path_val = _skill_path(game_id)
        self._write_skill(skill_path_val, transport_url, probe_schemas, explorer_raw, protocol_def)
        skill_path_val = validate_skill_loop(
            self.role,
            self.llm,
            game_id,
            skill_path_val,
            transport_url,
            probe_schemas,
            explorer_raw,
            protocol_def,
            self._write_skill,
        )
        skill_module = self._load_skill(game_id, skill_path_val)
        self.mcp_skill = skill_module
        self.protocol_model = {
            "discovered": True,
            "peer_url": peer_url,
            "transport_url": transport_url,
            "skill_path": str(skill_path_val),
            "tools": list(probe_schemas.keys()),
            "explorer_mapping": explorer_raw,
            "protocol_def": protocol_def,
        }
        logger.info(f"[{self.role}] Discovery done. Skill loaded from {skill_path_val}.")

    def _probe_full(self, peer_url: str) -> tuple[str, dict, dict | None]:
        from agent.tools.mcp_probe_tool import _probe_sync

        base = peer_url.rstrip("/")
        transport_url, result, protocol_def = _probe_sync(base)
        has_proto = protocol_def is not None
        logger.info(
            f"[{self.role}] Probed {base}: transport={transport_url}, "
            f"tools={list(result)}, protocol_def={'yes' if has_proto else 'no'}"
        )
        return transport_url, result, protocol_def

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
