"""crewAI tools for game orchestration."""

from agent.tools.board_tool import (
    apply_both_moves,
    apply_move,
    check_board_state,
    get_legal_moves,
)
from agent.tools.game_state_tool import (
    get_observation,
    load_game_state,
    save_game_state,
)
from agent.tools.protocol_tool import (
    analyze_tool_names,
    infer_game_flow,
    summarize_protocol,
)
from agent.tools.mcp_probe_tool import probe_mcp_server
from agent.tools.read_skill_tool import read_skill_file
from agent.tools.strategy_tool import call_strategy

__all__ = [
    # Strategy
    "call_strategy",
    # MCP Discovery
    "probe_mcp_server",
    "read_skill_file",
    # Game State
    "get_observation",
    "load_game_state",
    "save_game_state",
    # Board
    "apply_move",
    "apply_both_moves",
    "get_legal_moves",
    "check_board_state",
    # Protocol Discovery
    "analyze_tool_names",
    "infer_game_flow",
    "summarize_protocol",
]
