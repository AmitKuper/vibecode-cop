"""crewAI Agents for game orchestration."""

from agent.agents.game_manager_agent import (
    create_game_manager_agent,
    create_update_state_task,
    create_verify_commitment_task,
)
from agent.agents.mcp_explorer_agent import (
    create_mcp_explorer_agent,
    create_mcp_explorer_task,
    create_skill_validator_agent,
    create_skill_validator_task,
)
from agent.agents.protocol_discovery_agent import (
    create_analyze_protocol_task,
    create_protocol_discovery_agent,
    create_verify_protocol_task,
)
from agent.agents.strategy_agent import (
    create_select_move_task,
    create_strategy_agent,
)

__all__ = [
    # Strategy Agent
    "create_strategy_agent",
    "create_select_move_task",
    # MCP Explorer + Validator
    "create_mcp_explorer_agent",
    "create_mcp_explorer_task",
    "create_skill_validator_agent",
    "create_skill_validator_task",
    # Game Manager Agent
    "create_game_manager_agent",
    "create_update_state_task",
    "create_verify_commitment_task",
    # Protocol Discovery Agent
    "create_protocol_discovery_agent",
    "create_analyze_protocol_task",
    "create_verify_protocol_task",
]
