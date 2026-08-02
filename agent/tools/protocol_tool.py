"""Tools for protocol discovery and analysis."""

import logging

try:
    from crewai.tools import tool
except ImportError:

    def tool(func):
        return func


logger = logging.getLogger(__name__)


@tool
def analyze_tool_names(tool_names: list[str]) -> str:
    """Analyze tool names to understand game protocol flow.

    Args:
        tool_names: List of available tool names

    Returns:
        Analysis of what each tool likely does based on its name
    """
    analysis = []

    for tool_name in tool_names:
        tl = tool_name.lower()
        if "start" in tl or "init" in tl or "begin" in tl:
            analysis.append(f"  {tool_name}: Likely initiates/starts the game or a game turn")
        elif "commit" in tl:
            analysis.append(f"  {tool_name}: Likely submits a move commitment (crypto hash)")
        elif "reveal" in tl or "move" in tl or "action" in tl:
            analysis.append(f"  {tool_name}: Likely reveals the actual move or performs an action")
        elif "audit" in tl or "verify" in tl or "check" in tl:
            analysis.append(f"  {tool_name}: Likely verifies/audits moves or game state")
        elif "ping" in tl or "health" in tl:
            analysis.append(f"  {tool_name}: Likely a health check or keep-alive")
        else:
            analysis.append(f"  {tool_name}: Unknown purpose, likely game-specific")

    result = "Tool Analysis:\n" + "\n".join(analysis)
    logger.info(result)
    return result


@tool
def infer_game_flow(available_tools: list[str]) -> str:
    """Infer the game flow from available tools.

    Args:
        available_tools: List of available tool names

    Returns:
        Inferred game flow sequence
    """
    tool_set = {t.lower() for t in available_tools}

    # Check for common protocol patterns
    if "start_game" in tool_set and "action" in tool_set:
        # Standard two-phase protocol: handshake + turn actions
        if "commit" in tool_set and "reveal" in tool_set:
            flow = "Commit-Reveal Protocol: start_game → (commit → reveal)* → audit"
        else:
            flow = "Simple Protocol: start_game → action* → (audit/end)"
    elif any("commit" in t for t in tool_set) and any("reveal" in t for t in tool_set):
        flow = "Commit-Reveal Game: likely moves are hidden then revealed"
    else:
        flow = "Unknown Protocol: tools are non-standard"

    logger.info(f"Inferred flow: {flow}")
    return flow


@tool
def summarize_protocol(tool_names: list[str], tool_schemas: dict = None) -> str:
    """Summarize the discovered protocol into a readable model.

    Args:
        tool_names: List of available tool names
        tool_schemas: Optional tool schema information

    Returns:
        Summary of the protocol model
    """
    summary_lines = []
    summary_lines.append("Protocol Summary:")
    summary_lines.append(f"  Total tools: {len(tool_names)}")
    summary_lines.append(f"  Available: {', '.join(tool_names)}")

    # Categorize tools
    game_control = [
        t for t in tool_names if any(x in t.lower() for x in ["start", "init", "begin", "end"])
    ]
    move_tools = [
        t for t in tool_names if any(x in t.lower() for x in ["move", "action", "commit", "reveal"])
    ]
    verification = [
        t for t in tool_names if any(x in t.lower() for x in ["verify", "audit", "check"])
    ]
    health = [t for t in tool_names if any(x in t.lower() for x in ["ping", "health"])]

    if game_control:
        summary_lines.append(f"  Game Control: {game_control}")
    if move_tools:
        summary_lines.append(f"  Move/Action: {move_tools}")
    if verification:
        summary_lines.append(f"  Verification: {verification}")
    if health:
        summary_lines.append(f"  Health/Status: {health}")

    result = "\n".join(summary_lines)
    logger.info(result)
    return result
