"""crewAI crew setup, RL-model fast path, and LLM-driven move selection mixin.

Helpers (RL cache, move parsing, observation building) are in orchestrator_crew_helpers.py.
"""

import logging

try:
    from crewai import Crew
except Exception:
    Crew = None  # type: ignore[assignment,misc]

from agent.orchestrator_crew_helpers import (
    _VALID_MOVES,
    build_observation,
    get_rl_policy,
    parse_move,
)

logger = logging.getLogger(__name__)


class CrewMixin:
    """Mixin providing crew creation and LLM-driven move selection."""

    role: str
    llm: object
    crews: dict

    def _get_token_counter(self):
        if not hasattr(self, "_token_counter"):
            from agent.llm.token_counter import TokenCounter

            self._token_counter = TokenCounter()
        return self._token_counter

    def _create_crew(self, game_id: str) -> "Crew":
        """Create a crewAI Crew for a game. Raises if LLM is not configured."""
        if self.llm is None:
            raise RuntimeError(
                f"No LLM configured for {self.role}. "
                "Set [llm] provider and model in your config file."
            )
        if Crew is None:
            raise RuntimeError("crewai is not installed. Install it with: pip install crewai")
        try:
            from agent.agents import create_select_move_task, create_strategy_agent
        except ImportError as exc:
            raise RuntimeError(f"crewai dependencies missing: {exc}") from exc
        logger.info(f"Creating crewAI crew for game {game_id}")
        strategy_agent = create_strategy_agent(llm=self.llm)
        task = create_select_move_task(strategy_agent)
        crew = Crew(agents=[strategy_agent], tasks=[task], verbose=False)
        self.crews[game_id] = crew
        return crew

    def _get_or_create_crew(self, game_id: str) -> Crew:
        if game_id not in self.crews:
            return self._create_crew(game_id)
        return self.crews[game_id]

    def _select_move_rl(self, observation: dict) -> str | None:
        """Select a move from the trained RL policy (~1 ms, no LLM).

        Returns a short move token or None if no RL model is available.
        """
        policy = get_rl_policy(self.role)
        if policy is None:
            return None
        board_state = observation.get("grid_state", {})
        if not board_state:
            return None
        last_revealed_cop_pos = observation.get("last_revealed_cop_pos")
        try:
            long_move = policy.select_move_from_dict(
                board_state, last_revealed_cop_pos=last_revealed_cop_pos
            )
            short_move = self._short_move(long_move)
            candidates = observation.get("candidate_actions", list(_VALID_MOVES))
            if short_move not in candidates:
                logger.debug(f"[{self.role}] RL move {short_move} not in candidates, using first")
                return candidates[0] if candidates else "STAY"
            logger.info(f"[{self.role}] RL policy → {short_move}")
            return short_move
        except Exception as exc:
            logger.warning(f"[{self.role}] RL inference failed: {exc}")
            return None

    def _select_move_llm(self, game_id: str, observation: dict) -> str:
        """Select a move by invoking the crewAI strategy crew (sync, use outside async)."""
        crew = self._get_or_create_crew(game_id)
        candidates = observation.get("candidate_actions", list(_VALID_MOVES))
        inputs = self._build_crew_inputs(observation, candidates)
        result = crew.kickoff(inputs=inputs)
        self._get_token_counter().record_from_crew_output(result)
        move = parse_move(result.raw, candidates)
        logger.info(f"[{self.role}] LLM selected move: {move} (raw={result.raw!r})")
        return move

    async def _select_move_llm_async(self, game_id: str, observation: dict) -> str:
        """Select a move via crewAI using kickoff_async (safe inside async context)."""
        crew = self._get_or_create_crew(game_id)
        candidates = observation.get("candidate_actions", list(_VALID_MOVES))
        inputs = self._build_crew_inputs(observation, candidates)
        result = await crew.kickoff_async(inputs=inputs)
        self._get_token_counter().record_from_crew_output(result)
        move = parse_move(result.raw, candidates)
        logger.info(f"[{self.role}] LLM selected move: {move} (raw={result.raw!r})")
        return move

    def _build_crew_inputs(self, observation: dict, candidates: list) -> dict:
        return {
            "role": self.role,
            "own_position": observation.get("own_position", [0, 0]),
            "turn": observation.get("turn", 0),
            "max_turns": getattr(self, "max_turns", 35),
            "candidate_actions": candidates,
            "scent_field": observation.get("scent_field", []),
            "board_state": observation.get("grid_state", {}),
        }

    def _build_observation(self, game_state: dict) -> dict:
        return build_observation(self.role, game_state)

    def _long_move(self, short: str) -> str:
        return {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST", "STAY": "STAY"}.get(
            short, short
        )

    def _short_move(self, long: str) -> str:
        return {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W", "STAY": "STAY"}.get(
            long, long
        )
