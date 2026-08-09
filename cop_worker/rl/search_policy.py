"""Serving adapter: minimax pursuit/evasion over exact chebyshev tracking, RL fallback.

Drops into the exact seam ``RLMover.decide`` already uses — ``select_action(observation,
belief, legal_actions)`` + ``reset()`` — so the match loop, episode reset, and legal
masking stay untouched. Every turn it tries to read the opponent's EXACT cell off the
received frame (``chebyshev_tracker``); with a fix it plays the depth-limited minimax
(``pursuit_search``), otherwise it falls back to the wrapped RL policy (or last-known
cell if there is no wrapped policy). Hints are never read — movement stays provably
hint-independent.
"""

from __future__ import annotations

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.chebyshev_tracker import exact_opponent_cell
from cop_worker.rl.pursuit_search import best_cop_action, best_thief_action


class SearchRolePolicy:
    """Minimax-first policy for one role; ``fallback`` is an optional RL policy."""

    def __init__(self, role: str, *, depth: int = 3, fallback=None,
                 max_steps: int = 35, barriers_max: int = 14) -> None:
        if role not in {"cop", "thief"}:
            raise ValueError(f"role must be cop/thief, got {role!r}")
        self.role = role
        self.depth = depth
        self.fallback = fallback
        self.max_steps = max_steps
        self.barriers_max = barriers_max
        self._last_seen: tuple[int, int] | None = None

    def reset(self) -> None:
        self._last_seen = None
        if self.fallback is not None:
            self.fallback.reset()

    def select_action(
        self,
        observation: LocalObservation,
        belief: BeliefState,
        legal_actions: list[str],
    ) -> str:
        if not legal_actions:
            raise RuntimeError("canonical domain returned no legal actions")
        opp = exact_opponent_cell(observation.opponent_scent, observation.grid_size)
        if opp is None:
            opp = self._last_seen  # coast on the last fix for a malformed frame
        else:
            self._last_seen = opp
        if opp is None:
            if self.fallback is not None:
                return self.fallback.select_action(observation, belief, legal_actions)
            return "STAY" if "STAY" in legal_actions else legal_actions[0]

        own = tuple(observation.own_position)
        barriers = [tuple(b) for b in observation.known_barriers]
        steps_left = max(1, self.max_steps - int(observation.step) + 1)
        if self.role == "cop":
            action = best_cop_action(
                own, opp, barriers,
                barriers_left=int(observation.own_barriers_remaining),
                steps_left=steps_left, depth=self.depth,
                n=observation.grid_size,
            )
        else:
            # The cop's spent walls are visible on the board; the rest can still come.
            action = best_thief_action(
                opp, own, barriers, steps_left=steps_left, depth=self.depth,
                n=observation.grid_size,
                cop_barriers_left=max(0, self.barriers_max - len(barriers)),
            )
        if action in legal_actions:
            return action
        if self.fallback is not None:
            return self.fallback.select_action(observation, belief, legal_actions)
        return "STAY" if "STAY" in legal_actions else legal_actions[0]


def wrap_with_search(policy, role: str, terms: dict | None = None, *, depth: int = 4):
    """Wrap a loaded RL policy in the minimax-first adapter (serving entry point).

    Depth 4 measured 2026-08-10: cop d4 captures thief d4 4/4 (mean step 18) at
    ~3s/half-move — decisive and far inside the 180s turn budget; thief d4 survives
    every non-search cop tested. Lower to 3 only if latency ever becomes a concern.
    """
    terms = terms or {}
    return SearchRolePolicy(
        "cop" if role in {"police", "cop"} else "thief",
        depth=depth,
        fallback=policy,
        max_steps=int(terms.get("max_steps", 35)),
        barriers_max=int(terms.get("barriers_max", 14)),
    )
