"""RL move engine — the whole point: real trained policy, never random."""

from __future__ import annotations

from ref3_match.mover_mixin import MoverStateMixin
from ref3_match.runtime_cfg import _PLACE_DELTAS, REPO_ROOT


class RLMover(MoverStateMixin):
    """Wraps the trained role policy and tracks own position + emitted scent."""

    def __init__(
        self,
        role: str,
        terms: dict,
        scent_model: str = "multiplicative_book_v1",
        move_policy: str = "rl",
    ) -> None:
        from cop_worker.board import Board
        from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS

        # Architecture-dispatching loader: the cop is RecurrentA2C-GRU and the thief may be a
        # DuelingDoubleDQN — load_counted_policy handles both (delegates recurrent internally).
        from cop_worker.rl.counted_policy import load_counted_policy

        self.role = role  # "police" (cop) or "thief"
        self.terms = terms
        self.scent_model = scent_model
        self.grid = terms["board_size"]
        self.actions = COP_ACTIONS if role == "police" else THIEF_ACTIONS
        # Role-split: our cop model lives in this repo; our thief model in the
        # sibling thief repo. Each worker owns its own trained policy.
        if role == "police":
            manifest = REPO_ROOT / "models" / "MANIFEST.json"
            manifest_role = "cop"
        else:
            manifest = REPO_ROOT.parent / "vibecode-thief" / "models" / "MANIFEST.json"
            manifest_role = "thief"
        self.policy = load_counted_policy(manifest, manifest_role)
        # Hybrid serving: minimax over exact chebyshev tracking with the RL policy as
        # fallback for blind frames. Only meaningful when the locked model makes the
        # frame an oracle; the plain RL path stays byte-identical under "rl".
        if move_policy in ("hybrid_search", "hybrid_search_belief"):
            from cop_worker.rl.search_wrap import wrap_with_search

            self.policy = wrap_with_search(
                self.policy,
                manifest_role,
                terms,
                belief_mode=(move_policy == "hybrid_search_belief"),
                scent_model=scent_model,
            )
        elif move_policy != "rl":
            raise ValueError(f"unknown move_policy {move_policy!r}")
        start = terms["cop_start"] if role == "police" else terms["thief_start"]
        self.pos = [int(start[0]), int(start[1])]  # [x, y]
        # Cop barrier state (thief never places): quota, placed cells, last placement.
        self.barriers_remaining = int(terms.get("barriers_max", 0)) if role == "police" else 0
        self.barriers: list[list[int]] = []
        self.last_barrier: list[int] | None = None
        # A board whose "thief" cell we drive to OUR position, so update_scent emits
        # the byte-exact book field around us regardless of role.
        self._board = Board(cop_position=[0, 0], thief_position=list(self.pos), grid_size=self.grid)
        from cop_worker.rules_engine import RulesEngine

        self._rules = RulesEngine(self._board, max_turns=terms["max_steps"])
        # Locked-model dispatch for our own emission: under subtractive_chebyshev_v1 the
        # trail lives in ChebyshevTrail (kit-exact rings/merge-by-max/subtractive decay,
        # 0.8-peak wire snapshots); the book engine above stays for multiplicative_book_v1.
        self._chebyshev_trail = None
        if scent_model == "subtractive_chebyshev_v1":
            from cop_worker.scent_chebyshev import ChebyshevTrail

            self._chebyshev_trail = ChebyshevTrail(
                self.grid,
                field_size=int(terms.get("smell_grid_size", 5)),
                emit_intensity=float(terms.get("emit_intensity", 0.9)),
                decay_per_step=float(terms.get("decay_per_step", 0.1)),
                min_center_intensity=float(terms.get("min_center_intensity", 0.5)),
            )

    def decide(self, step: int, sub_game: int, opponent_smell: dict, opponent_hint: str) -> str:
        """Return the RL-chosen action for this step (never random)."""
        from cop_worker.observation import BeliefState, LocalObservation

        obs = LocalObservation(
            own_position=(self.pos[0], self.pos[1]),
            own_barriers_remaining=self.barriers_remaining,
            known_barriers=[tuple(b) for b in self.barriers],
            opponent_scent=self._opponent_scent_grid(opponent_smell),
            last_hint=opponent_hint or "",
            step=step,
            gamelet=sub_game,
            grid_size=self.grid,
        )
        belief = BeliefState.uniform(self.grid, step=step)
        # Pass the TRUE legal action set (board edges + barriers + quota), matching training.
        # The full list let the policy propose off-board moves the domain clamps to STAY, which
        # froze the cop at its start cell (never pursuing). Mask per role.
        from cop_worker.rl.action_space import (
            compute_legal_mask_cop,
            compute_legal_mask_thief,
        )

        if self.role == "police":
            mask = compute_legal_mask_cop(
                tuple(self.pos),
                [tuple(b) for b in self.barriers],
                self.barriers_remaining,
                self.grid,
            )
        else:
            mask = compute_legal_mask_thief(
                tuple(self.pos),
                [tuple(b) for b in self.barriers],
                self.grid,
            )
        legal = [a for a, m in zip(self.actions, mask) if m] or list(self.actions)
        action = self.policy.select_action(obs, belief, legal)
        return action

    def apply(self, action: str) -> None:
        """Apply the chosen action: move (N/S/E/W), STAY, or place a barrier.

        A PLACE_* forfeits movement (position unchanged) and, if legal (quota left,
        target in-bounds and not already blocked), records the barrier cell so it goes
        on the wire as barrier_placed and is fed back into the next observation.
        """
        self.last_barrier = None
        if action in _PLACE_DELTAS:
            if self.role == "police" and self.barriers_remaining > 0:
                dx, dy = _PLACE_DELTAS[action]
                bx, by = self.pos[0] + dx, self.pos[1] + dy
                if 0 <= bx < self.grid and 0 <= by < self.grid and [bx, by] not in self.barriers:
                    self.barriers.append([bx, by])
                    self.barriers_remaining -= 1
                    self.last_barrier = [bx, by]
            return  # placement (legal or not) forfeits the move
        x, y = self.pos
        if action == "N" and y > 0:
            y -= 1
        elif action == "S" and y < self.grid - 1:
            y += 1
        elif action == "E" and x < self.grid - 1:
            x += 1
        elif action == "W" and x > 0:
            x -= 1
        self.pos = [x, y]
