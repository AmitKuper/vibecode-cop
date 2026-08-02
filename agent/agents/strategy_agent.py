"""crewAI Agent for selecting moves in the Cop & Thief game via RL model."""

from typing import Any


def create_strategy_agent(llm: Any):
    """Create the move-selection agent.

    The agent calls the `call_strategy` tool, which loads the trained RL model
    (cop_ppo_league_best.pt / thief_ppo_league_best.pt) and returns the optimal
    move. The LLM orchestrates the tool call and returns the result verbatim.
    If no RL model is found the tool raises and the LLM must reason from the
    board description.

    Args:
        llm: crewai.LLM instance (Ollama, Anthropic, etc.)
    """
    import crewai  # lazy import so test stubs in sys.modules take effect

    from agent.tools.strategy_tool import call_strategy

    return crewai.Agent(
        role="Game Strategist",
        goal=(
            "Call the call_strategy tool with the current observation to get the "
            "optimal move. Return ONLY the move token: N, S, E, W, or STAY."
        ),
        backstory=(
            "You play Cop & Thief on a 7×7 grid. You have access to a trained RL "
            "policy via the call_strategy tool. Always call the tool first — it will "
            "return the best move from the trained model. If the tool is unavailable, "
            "reason about the board yourself: cop chases thief (capture = same cell), "
            "thief evades until max_turns. Moves: N=row-1, S=row+1, E=col+1, W=col-1."
        ),
        tools=[call_strategy],
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )


def create_select_move_task(agent):
    """Create the per-turn move-selection task."""
    import crewai  # lazy import so test stubs in sys.modules take effect

    return crewai.Task(
        description=(
            "Select the next move for role={role}.\n"
            "Board state:\n"
            "  Your position : {own_position}\n"
            "  Turn          : {turn} / {max_turns}\n"
            "  Legal moves   : {candidate_actions}\n"
            "  Scent field   : {scent_field}\n\n"
            "Step 1: call the call_strategy tool with this observation dict:\n"
            "  {{'role': '{role}', 'candidate_actions': {candidate_actions},\n"
            "   'own_position': {own_position}, 'turn': {turn},\n"
            "   'board_state': {board_state}}}\n\n"
            "Step 2: return EXACTLY the move token the tool gave you.\n"
            "No explanation. No punctuation. Just the token (N / S / E / W / STAY)."
        ),
        agent=agent,
        expected_output="One of: N, S, E, W, STAY",
    )
