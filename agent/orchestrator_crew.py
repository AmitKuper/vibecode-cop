"""crewAI crew setup, RL-model fast path, and LLM-driven move selection mixin."""

import logging
import re
from pathlib import Path

try:
    from crewai import Crew
except ModuleNotFoundError:
    Crew = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

_VALID_MOVES = {"N", "S", "E", "W", "STAY"}
_LONG_TO_SHORT = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W", "STAY": "STAY"}

_rl_policies: dict = {}


def _get_rl_policy(role: str):
    """Load and cache the best RL policy for *role*. Returns None if unavailable."""
    if role in _rl_policies:
        return _rl_policies[role]
    try:
        from agent.rl.policy import RLPolicy
        policy = RLPolicy.load(role, models_dir=Path("models"))
        _rl_policies[role] = policy
        logger.info(f"[CrewMixin] Loaded RL policy for {role}")
        return policy
    except Exception as exc:
        logger.warning(f"[CrewMixin] RL policy unavailable for {role}: {exc}")
        _rl_policies[role] = None
        return None


def _parse_move(raw: str, candidates: list[str]) -> str:
    """Extract a valid move token from LLM raw output.

    Tries exact match first, then scans for a token in candidates.
    Raises ValueError if no valid move can be found.
    """
    text = raw.strip().upper()
    # Normalise long-form words
    for long, short in _LONG_TO_SHORT.items():
        text = re.sub(rf"\b{long}\b", short, text)

    # Exact single-token match
    if text in _VALID_MOVES:
        return text

    # Scan for any candidate token in the output
    for token in candidates:
        if re.search(rf"\b{token}\b", text):
            return token

    raise ValueError(f"No valid move in LLM output: {raw!r}. Candidates: {candidates}")


class CrewMixin:
    """Mixin providing crew creation and LLM-driven move selection."""

    role: str
    llm: object
    crews: dict

    def _create_crew(self, game_id: str) -> "Crew":
        """Create a crewAI Crew for a game. Raises if LLM is not configured."""
        if Crew is None:
            raise RuntimeError(
                "crewai is not installed. Install it with: pip install crewai"
            )
        from agent.agents import create_select_move_task, create_strategy_agent

        if self.llm is None:
            raise RuntimeError(
                f"No LLM configured for {self.role}. "
                "Set [llm] provider and model in your config file."
            )

        logger.info(f"Creating crewAI crew for game {game_id}")
        strategy_agent = create_strategy_agent(llm=self.llm)
        task = create_select_move_task(strategy_agent)
        crew = Crew(agents=[strategy_agent], tasks=[task], verbose=False)
        self.crews[game_id] = crew
        return crew

    def _get_or_create_crew(self, game_id: str) -> Crew:
        """Return existing crew or create a new one for the given game."""
        if game_id not in self.crews:
            return self._create_crew(game_id)
        return self.crews[game_id]

    def _select_move_rl(self, observation: dict) -> str | None:
        """Select a move from the trained RL policy (~1 ms, no LLM).

        Returns a short move token ('N','S','E','W','STAY') or None if no
        RL model is available (caller should fall back to LLM).
        """
        policy = _get_rl_policy(self.role)
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
                logger.debug(
                    f"[{self.role}] RL move {short_move} not in candidates {candidates}, "
                    "using first legal"
                )
                return candidates[0] if candidates else "STAY"
            logger.info(f"[{self.role}] RL policy → {short_move}")
            return short_move
        except Exception as exc:
            logger.warning(f"[{self.role}] RL inference failed: {exc}")
            return None

    def _select_move_llm(self, game_id: str, observation: dict) -> str:
        """Select a move by invoking the crewAI strategy crew.

        Args:
            game_id: Active game identifier (crew is cached per game).
            observation: Board observation dict built by _build_observation().

        Returns:
            Short move token: 'N', 'S', 'E', 'W', or 'STAY'.

        Raises:
            RuntimeError: If the LLM returns an unparseable response.
        """
        crew = self._get_or_create_crew(game_id)
        candidates = observation.get("candidate_actions", list(_VALID_MOVES))

        inputs = {
            "role": self.role,
            "own_position": observation.get("own_position", [0, 0]),
            "turn": observation.get("turn", 0),
            "max_turns": getattr(self, "max_turns", 35),
            "candidate_actions": candidates,
            "scent_field": observation.get("scent_field", []),
            "board_state": observation.get("grid_state", {}),
        }

        logger.debug(f"[{self.role}] Asking LLM for move. Turn={inputs['turn']}, "
                     f"pos={inputs['own_position']}, legal={candidates}")
        result = crew.kickoff(inputs=inputs)
        move = _parse_move(result.raw, candidates)
        logger.info(f"[{self.role}] LLM selected move: {move} (raw={result.raw!r})")
        return move

    def _build_observation(self, game_state: dict) -> dict:
        """Build observation dict from game state for this agent's role."""
        cop_pos = game_state.get("cop_position", [0, 0])
        thief_pos = game_state.get("thief_position", [6, 6])
        turn = game_state.get("turn", 0)
        own_pos = cop_pos if self.role == "cop" else thief_pos
        x, y = own_pos
        candidates = []
        if x > 0:
            candidates.append("W")
        if x < 6:
            candidates.append("E")
        if y > 0:
            candidates.append("N")
        if y < 6:
            candidates.append("S")
        candidates.append("STAY")
        obs = {
            "own_position": own_pos,
            "candidate_actions": candidates,
            "turn": turn,
            "scent_field": game_state.get("scent_field", []),
            "grid_state": game_state,
        }
        if self.role == "thief":
            obs["last_revealed_cop_pos"] = game_state.get("last_revealed_cop_pos")
        return obs

    def _long_move(self, short: str) -> str:
        return {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST", "STAY": "STAY"}.get(
            short, short
        )

    def _short_move(self, long: str) -> str:
        return {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W", "STAY": "STAY"}.get(
            long, long
        )
