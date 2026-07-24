"""crewAI Agent for discovering and understanding game protocols."""

from typing import Any

from crewai import Agent, Task


def create_protocol_discovery_agent(llm: Any) -> Agent:
    """Create an agent for discovering MCP game protocols.

    This agent:
    - Analyzes available tools from opponent's MCP server
    - Understands the game flow and protocol phases
    - Determines tool call sequence and parameters
    - Builds a model of the game protocol

    Args:
        llm: Optional custom LLM instance (uses crewAI default if None)

    Returns:
        Agent configured for protocol exploration
    """
    agent = Agent(
        role="Protocol Analyst",
        goal=(
            "Understand the opponent's MCP game protocol by analyzing available tools "
            "and their schemas, then determine the correct sequence of tool calls and "
            "parameters needed to play the game."
        ),
        backstory=(
            "You are a protocol analyst specializing in game APIs and MCP interfaces. "
            "Given tools from an opponent's MCP server, you can deduce the game flow, "
            "understand what parameters each tool expects, and figure out how to play the "
            "game correctly. You reason about tool names, schemas, and typical game patterns "
            "to build a complete protocol model."
        ),
        verbose=True,
        allow_delegation=False,
        llm=llm,
    )
    return agent


def create_analyze_protocol_task(agent):
    """Create task for analyzing discovered protocol.

    Args:
        agent: The ProtocolDiscoveryAgent

    Returns:
        Task for protocol analysis
    """
    task = Task(
        description=(
            "Analyze the discovered MCP tools and build a model of the game protocol. "
            "You will receive: "
            "1. List of available tools: {available_tools} "
            "2. Tool schemas (if available): {tool_schemas} "
            "3. Hint about game type (cop vs thief): {game_type} "
            "\n"
            "Your analysis should determine: "
            "- What is the game flow? (e.g., handshake → commit → reveal → audit) "
            "- What does each tool do based on its name and schema? "
            "- What parameters does each tool expect? "
            "- In what order should tools be called? "
            "- What messages need to be passed between tools? "
            "\n"
            "Provide a detailed protocol model explaining the game flow, tool purposes, "
            "and the sequence of operations needed to play."
        ),
        agent=agent,
        expected_output=(
            "A detailed protocol model describing: "
            "(1) Game phases/flow "
            "(2) What each tool does "
            "(3) Tool call sequence "
            "(4) Required parameters for each tool "
            "(5) Expected responses from each tool"
        ),
    )
    return task


def create_verify_protocol_task(agent):
    """Create task for verifying protocol understanding.

    Args:
        agent: The ProtocolDiscoveryAgent

    Returns:
        Task for protocol verification
    """
    task = Task(
        description=(
            "Verify your understanding of the game protocol by checking consistency "
            "and completeness. Protocol model to verify: {protocol_model} "
            "\n"
            "Check: "
            "- Are all available tools accounted for? "
            "- Does the flow make sense for a game? "
            "- Are there any gaps or unclear tool purposes? "
            "- Are the parameter types and names consistent? "
            "- Is the sequence of tool calls logical? "
            "\n"
            "Return a verification report with any issues found and confidence level."
        ),
        agent=agent,
        expected_output=(
            "A verification report including: "
            "(1) Completeness check "
            "(2) Consistency check "
            "(3) Any gaps or issues found "
            "(4) Confidence level (0-100%) "
            "(5) Recommended protocol model"
        ),
    )
    return task
