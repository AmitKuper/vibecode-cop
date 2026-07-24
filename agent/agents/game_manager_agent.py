"""crewAI Agent for managing game state and verification."""

from typing import Any

from crewai import Agent, Task


def create_game_manager_agent(llm: Any) -> Agent:
    """Create an agent for managing game state and verification.

    Responsibilities:
    - Verify commitment hashes
    - Apply moves to board state
    - Check win/loss conditions
    - Update game state

    Args:
        llm: Optional custom LLM instance (uses crewAI default if None)

    Returns:
        Agent configured for game management
    """
    agent = Agent(
        role="Game Manager",
        goal="Manage game state, verify moves, and ensure fair play",
        backstory=(
            "You are a game manager for a Cop and Thief game. "
            "Your role is to manage game state, verify player commitments, "
            "apply moves to the board, and maintain the integrity of the game. "
            "You ensure all moves are valid and the game state is consistent."
        ),
        verbose=True,
        allow_delegation=False,
        llm=llm,
    )
    return agent


def create_update_state_task(agent):
    """Create task for updating game state after moves.

    Args:
        agent: The GameManagerAgent

    Returns:
        Task for state update
    """
    task = Task(
        description=(
            "You will receive game_state, cop_move, and thief_move in the inputs. "
            "Use the apply_both_moves tool to apply both moves to the board. "
            "Return the updated game state dict. "
            "Game State: {game_state} "
            "Cop Move: {cop_move} "
            "Thief Move: {thief_move}"
        ),
        agent=agent,
        expected_output="Updated game state dict with new positions and turn counter",
    )
    return task


def create_verify_commitment_task(agent):
    """Create task for verifying commitments.

    Args:
        agent: The GameManagerAgent

    Returns:
        Task for commitment verification
    """
    task = Task(
        description=(
            "You will receive a commitment hash (h_commit) and the revealed move+nonce. "
            "Your job is to verify that the revealed move's hash matches the commitment. "
            "Use the verify_commitment tool to check. "
            "Commitment: {commitment} "
            "Revealed Move: {revealed_move} "
            "Nonce: {nonce}"
        ),
        agent=agent,
        expected_output="Verification result: 'VERIFIED' or 'INVALID'",
    )
    return task
