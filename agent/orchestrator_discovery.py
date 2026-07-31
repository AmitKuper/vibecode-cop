"""Protocol discovery mixin — runs once at game start.

Flow:
  1. Python probes the peer's MCP server (auto-detects SSE transport URL).
  2. MCPExplorerAgent (crewAI + LLM) analyses probe output and produces a
     protocol mapping (tool names, param names, signing, field_map).
  3. Python generates agent/skills/game_<id>_mcp.py from the mapping.
  4. SkillValidatorAgent reviews the file; on failure Python regenerates it.
  5. The skill module is imported; self.mcp_skill is set for the game.
  6. The skill file is deleted at game end (call cleanup_skill).

Sub-modules:
  orchestrator_discovery_render  — constants, path helpers, _render_skill
  orchestrator_discovery_write   — _write_skill_from_*, _parse_explorer_mapping,
                                   python_validate_skill, run_validator_crew,
                                   validate_skill_loop
  orchestrator_discovery_mixin   — DiscoveryMixin class
"""

from agent.orchestrator_discovery_mixin import DiscoveryMixin
from agent.orchestrator_discovery_render import (
    _CANONICAL_FIELDS,
    _MAX_VALIDATION_ATTEMPTS,
    _SECRET_PLACEHOLDER,
    _SKILLS_DIR,
    _render_skill,
    _skill_module_name,
    _skill_path,
)
from agent.orchestrator_discovery_validate import (
    python_validate_skill,
    run_validator_crew,
    validate_skill_loop,
)
from agent.orchestrator_discovery_write import (
    _parse_explorer_mapping,
    _write_skill_from_mapping,
    _write_skill_from_schemas,
)

__all__ = [
    "DiscoveryMixin",
    "_CANONICAL_FIELDS",
    "_MAX_VALIDATION_ATTEMPTS",
    "_SECRET_PLACEHOLDER",
    "_SKILLS_DIR",
    "_render_skill",
    "_skill_module_name",
    "_skill_path",
    "_parse_explorer_mapping",
    "_write_skill_from_mapping",
    "_write_skill_from_schemas",
    "python_validate_skill",
    "run_validator_crew",
    "validate_skill_loop",
]
