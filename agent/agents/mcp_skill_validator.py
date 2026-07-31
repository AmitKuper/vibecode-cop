"""crewAI agents for MCP skill validation."""

from typing import Any

from crewai import Agent, Task

from agent.tools.read_skill_tool import read_skill_file


def create_skill_validator_agent(llm: Any) -> Agent:
    """Agent that validates the generated skill file."""
    return Agent(
        role="MCP Skill Validator",
        goal=(
            "Read the generated skill file using read_skill_file, verify it is "
            "syntactically correct Python, contains the three required async "
            "functions (start_game, action, ping), and that PEER_URL and "
            "SECRET are present. Report problems clearly."
        ),
        backstory=(
            "You are a code reviewer specialising in Python MCP adapters. "
            "You ensure generated skill files are valid and safe to import."
        ),
        tools=[read_skill_file],
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )


def create_skill_validator_task(agent: Agent) -> Task:
    """Task: validate the skill file and return structured feedback."""
    return Task(
        description=(
            "Use read_skill_file to read the skill at {skill_path}.\n"
            "Check all of:\n"
            "  1. syntax_ok is true (no Python syntax errors).\n"
            "  2. has_start_game is true.\n"
            "  3. has_action is true.\n"
            "  4. has_ping is true.\n"
            "  5. PEER_URL is present in the source.\n"
            "  6. SECRET = '__SECRET__' is present (literal placeholder).\n\n"
            'Return JSON: {{"valid": true/false, "issues": ["..."], '
            '"verdict": "PASS or short summary of problems"}}'
        ),
        agent=agent,
        expected_output="JSON with keys: valid (bool), issues (list[str]), verdict (str).",
        context=[],
    )
