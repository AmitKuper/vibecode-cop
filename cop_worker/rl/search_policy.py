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
from cop_worker.rl.line_escape import LineEscape
from cop_worker.rl.opponent_fix import OpponentFix
from cop_worker.rl.pursuit_search import best_cop_action, best_thief_action
from cop_worker.rl.stall_squeeze import StallSqueeze


class SearchRolePolicy:
    """Minimax-first policy for one role; ``fallback`` is an optional RL policy."""

    def __init__(
        self,
        role: str,
        *,
        depth: int = 3,
        fallback=None,
        max_steps: int = 35,
        barriers_max: int = 14,
        belief_mode: bool = False,
        belief_peak_threshold: float = 0.06,
        decode_book_scent: bool = False,
    ) -> None:
        if role not in {"cop", "thief"}:
            raise ValueError(f"role must be cop/thief, got {role!r}")
        self.role = role
        self.depth = depth
        self.fallback = fallback
        self.max_steps = max_steps
        self.barriers_max = barriers_max
        # Opt-in (``hybrid_search_belief``): with no oracle fix, the cop searches
        # over a live posterior instead of falling straight back to the net.
        self.belief_mode = belief_mode
        self.belief_peak_threshold = belief_peak_threshold
        self._belief_engine = None
        # decode_book_scent (per-pairing, from the locked scent model): also
        # invert multiplicative_book_v1 frames so the search stays sighted in
        # book-scent pairings; chebyshev pairings resolve byte-identically.
        self._fix = OpponentFix(decode_book_scent)
        self._squeeze = StallSqueeze() if self.role == "cop" else None
        self._escape = LineEscape() if self.role == "thief" else None

    def reset(self) -> None:
        self._fix.reset()
        self._belief_engine = None
        if self._squeeze is not None:
            self._squeeze.reset()
        if self._escape is not None:
            self._escape.reset()
        if self.fallback is not None:
            self.fallback.reset()

    def _live_posterior(self, observation: LocalObservation):
        from cop_worker.belief_engine import BeliefEngine

        if self._belief_engine is None:
            self._belief_engine = BeliefEngine(observation.grid_size, self.role)
        barriers = [tuple(b) for b in observation.known_barriers]
        self._belief_engine = self._belief_engine.predict(barriers).observe_scent(
            observation.opponent_scent, barriers
        )
        return self._belief_engine.belief

    def select_action(
        self,
        observation: LocalObservation,
        belief: BeliefState,
        legal_actions: list[str],
    ) -> str:
        if not legal_actions:
            raise RuntimeError("canonical domain returned no legal actions")
        opp = self._fix.fix(observation.opponent_scent, observation.grid_size)
        posterior = self._live_posterior(observation) if self.belief_mode else None
        if opp is None:
            if posterior is not None and self.role == "cop":
                from cop_worker.rl.belief_pursuit import belief_best_cop_action, belief_peak

                if belief_peak(posterior.prob) >= self.belief_peak_threshold:
                    action = belief_best_cop_action(
                        tuple(observation.own_position),
                        posterior.prob,
                        [tuple(b) for b in observation.known_barriers],
                        int(observation.own_barriers_remaining),
                        max(1, self.max_steps - int(observation.step) + 1),
                        depth=self.depth,
                        n=observation.grid_size,
                    )
                    if action in legal_actions:
                        return action
            if self.fallback is not None:
                return self.fallback.select_action(observation, belief, legal_actions)
            return "STAY" if "STAY" in legal_actions else legal_actions[0]

        own = tuple(observation.own_position)
        barriers = [tuple(b) for b in observation.known_barriers]
        steps_left = max(1, self.max_steps - int(observation.step) + 1)
        if self.role == "cop":
            # Anti-evader override first: a stalled minimax provably never
            # captures (open-board pursuit is thief-win), so a squeezing wall
            # strictly dominates whatever move it would have picked.
            squeeze = self._squeeze.override(
                own,
                opp,
                barriers,
                int(observation.own_barriers_remaining),
                steps_left,
                legal_actions,
            )
            if squeeze is not None:
                return squeeze
            action = best_cop_action(
                own,
                opp,
                barriers,
                barriers_left=int(observation.own_barriers_remaining),
                steps_left=steps_left,
                depth=self.depth,
                n=observation.grid_size,
            )
        else:
            # The cop's spent walls are visible on the board; the rest can still come.
            cop_left = max(0, self.barriers_max - len(barriers))
            action = best_thief_action(
                opp,
                own,
                barriers,
                steps_left=steps_left,
                depth=self.depth,
                n=observation.grid_size,
                cop_barriers_left=cop_left,
            )
            # Anti-partition override: if a wall line is forming and minimax's
            # move is doomed once it completes, cross while the gap exists.
            escape = self._escape.override(
                own, opp, barriers, cop_left, steps_left, action, legal_actions
            )
            if escape is not None:
                action = escape
        if action in legal_actions:
            return action
        if self.fallback is not None:
            return self.fallback.select_action(observation, belief, legal_actions)
        return "STAY" if "STAY" in legal_actions else legal_actions[0]
