"""The sighted search+hook teacher: production cop stack on exact state."""

from __future__ import annotations

from pathlib import Path

from cop_worker.rl.pursuit_search import best_cop_action
from cop_worker.rl.stall_squeeze import StallSqueeze

MAX_STEPS = 35


class SearchHookTeacher:
    """Exactly the production sighted pairing: StallSqueeze first, minimax after.

    Positions come from the true DomainState (the teacher is privileged); the
    student only ever sees the observation tensor, so this is the standard
    privileged-teacher / blind-student imitation setup.
    """

    def __init__(
        self, depth: int = 4, time_budget_s: float = 1.5, hook: bool = True, corridor: bool = True
    ) -> None:
        from cop_worker.rl.corridor_plan import CorridorPlan

        self.depth = depth
        self.time_budget_s = time_budget_s
        self.squeeze = StallSqueeze() if hook else None
        self.corridor = CorridorPlan() if (hook and corridor) else None

    def reset(self) -> None:
        if self.squeeze is not None:
            self.squeeze.reset()
        if self.corridor is not None:
            self.corridor.reset()

    def action(self, state, legal: list[str], obs=None) -> str:
        cop = tuple(state.cop_position)
        thief = tuple(state.thief_position)
        barriers = [tuple(b) for b in state.barriers]
        steps_left = max(1, MAX_STEPS - int(state.turn))
        if self.corridor is not None:
            act = self.corridor.override(
                cop, thief, barriers, int(state.cop_barriers_remaining), int(state.turn) + 1, legal
            )
            if act is not None:
                return act
        if self.squeeze is not None:
            act = self.squeeze.override(
                cop, thief, barriers, int(state.cop_barriers_remaining), steps_left, legal
            )
            if act is not None:
                return act
        act = best_cop_action(
            cop,
            thief,
            barriers,
            int(state.cop_barriers_remaining),
            steps_left,
            depth=self.depth,
            n=state.grid_size,
            time_budget_s=self.time_budget_s,
        )
        return act if act in legal else ("STAY" if "STAY" in legal else legal[0])


class ThiefStackTeacher:
    """The full production thief: minimax evasion + confined-mode escape."""

    def __init__(self, depth: int = 4, time_budget_s: float = 1.5) -> None:
        from cop_worker.rl.line_escape import LineEscape

        self.depth = depth
        self.time_budget_s = time_budget_s
        self.escape = LineEscape()

    def reset(self) -> None:
        self.escape.reset()

    def action(self, state, legal: list[str], obs=None) -> str:
        from cop_worker.rl.pursuit_search import best_thief_action

        cop = tuple(state.cop_position)
        thief = tuple(state.thief_position)
        barriers = [tuple(b) for b in state.barriers]
        cop_left = int(state.cop_barriers_remaining)
        steps_left = max(1, MAX_STEPS - int(state.turn))
        act = best_thief_action(
            cop,
            thief,
            barriers,
            steps_left,
            depth=self.depth,
            n=state.grid_size,
            cop_barriers_left=cop_left,
            time_budget_s=self.time_budget_s,
        )
        override = self.escape.override(thief, cop, barriers, cop_left, steps_left, act, legal)
        act = override or act
        return act if act in legal else ("STAY" if "STAY" in legal else legal[0])


class ChampionTeacher:
    """The manifest RL champion as expert — for the opponent families it was
    trained against, where it measurably beats the search stack (thief:
    belief_pursuit 0.78 vs our 0.37; targeted_exploit 0.78 vs 0.33)."""

    def __init__(self, role: str) -> None:
        import torch

        from cop_worker.rl.model_schema import load_manifest
        from cop_worker.rl.recurrent_policy import RecurrentActorCritic

        repo = Path(__file__).resolve().parents[2]
        if role == "thief":
            repo = repo.parent / "vibecode-thief"
        entry = load_manifest(str(repo / "models" / "MANIFEST.json"))[role]
        blob = torch.load(repo / "models" / entry.artifact, map_location="cpu", weights_only=False)
        sd = blob.get("state_dict", blob)
        self.net = RecurrentActorCritic(
            sd["encoder.0.weight"].shape[1], sd["policy_head.bias"].shape[0]
        )
        self.net.load_state_dict(sd)
        self.net.eval()
        self.role = role
        self._hidden = None

    def reset(self) -> None:
        self._hidden = None

    def action(self, state, legal: list[str], obs=None) -> str:
        import torch

        from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS

        actions = COP_ACTIONS if self.role == "cop" else THIEF_ACTIONS
        mask = torch.tensor([a in legal for a in actions], dtype=torch.bool)
        with torch.no_grad():
            logits, _v, self._hidden = self.net(obs.unsqueeze(0), self._hidden)
        return actions[int(logits[0].masked_fill(~mask, -1e9).argmax())]
