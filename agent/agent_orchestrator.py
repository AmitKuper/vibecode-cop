"""AgentOrchestrator — single composition root for all v7 subsystems."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.audit.step_journal import StepJournal
    from agent.runtime_mode import RuntimeMode

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Single composition root. Owns and composes all subsystems.
    All subsystem access goes through this class — nothing calls subsystems directly.
    """

    def __init__(
        self,
        role: str,  # "cop" or "thief"
        game_uid: str,
        grid_size: int,
        mode: RuntimeMode | None = None,
        work_dir: str = ".",
        config: dict | None = None,
    ):
        from agent.runtime_mode import RuntimeMode

        self.role = role
        self.game_uid = game_uid
        self.grid_size = grid_size
        self.mode = mode if mode is not None else RuntimeMode.DEVELOPMENT
        self.work_dir = work_dir
        self.config = config or {}

        # Validate mode requirements before instantiating anything
        if self.mode == RuntimeMode.COUNTED:
            self._validate_counted_preconditions()

        # Protocol state
        from agent.mcp.coordinator import get_coordinator

        self.coordinator = get_coordinator()

        # Observation and belief
        from agent.scent import ScentFields

        self.scent_fields: ScentFields = ScentFields.zeros(grid_size)

        from agent.belief_engine import BeliefEngine

        self.belief_engine: BeliefEngine = BeliefEngine(grid_size, role)

        # Reliability
        from agent.reliability.deadline_tracker import DeadlineTracker

        self.deadline_tracker: DeadlineTracker = DeadlineTracker(
            f"{work_dir}/deadlines_{game_uid}.json"
        )

        from agent.reliability.recovery_state import RecoveryStore

        self.recovery_store: RecoveryStore = RecoveryStore(f"{work_dir}/recovery_{game_uid}.json")

        # Audit
        self.step_journals: dict[int, object] = {}  # gamelet -> StepJournal

        # League
        from agent.step0.league_ledger import LeagueLedger

        self.league_ledger: LeagueLedger = LeagueLedger(f"{work_dir}/league_ledger.json")

        # GUI
        from agent.gui.live_view_model import LiveViewModel

        self.live_view: LiveViewModel = LiveViewModel(role, grid_size)

        logger.info(
            "AgentOrchestrator initialized role=%s mode=%s uid=%s",
            role,
            self.mode.value,
            game_uid,
        )

    def _validate_counted_preconditions(self) -> None:
        """Fail closed — raise ValueError if counted mode cannot proceed safely."""
        secret = self.config.get("secret", "")
        if not secret or secret in ("dev-secret-change-me", "change-me", ""):
            raise ValueError("COUNTED mode rejected: development/placeholder secret")

        # Only run git check if config explicitly enables it (avoids test fragility)
        if self.config.get("enforce_git_check", False):
            import subprocess

            try:
                sha = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], capture_output=True, text=True
                ).stdout.strip()
            except Exception:
                sha = "unknown"
            if not sha or sha == "unknown":
                raise ValueError("COUNTED mode rejected: git SHA unknown")

        model_sha = self.config.get("model_sha256", "placeholder")
        if model_sha in ("placeholder", "", "unknown"):
            raise ValueError("COUNTED mode rejected: placeholder/missing model SHA")

    def get_journal(self, gamelet: int) -> StepJournal:
        """Get or create per-gamelet step journal."""
        from agent.audit.step_journal import StepJournal

        if gamelet not in self.step_journals:
            path = f"{self.work_dir}/journal_{self.game_uid}_g{gamelet:02d}.json"
            self.step_journals[gamelet] = StepJournal(path)
        return self.step_journals[gamelet]  # type: ignore[return-value]

    def update_scent_and_belief(
        self,
        cop_pos: tuple[int, int],
        thief_pos: tuple[int, int],
        barriers: list[tuple[int, int]],
    ) -> None:
        """Update symmetric scent fields and Bayesian belief after each turn."""
        self.scent_fields = self.scent_fields.update(cop_pos, thief_pos)
        if self.role == "cop":
            obs_scent = self.scent_fields.cop_observation_scent()
        else:
            obs_scent = self.scent_fields.thief_observation_scent()
        self.belief_engine = self.belief_engine.predict(barriers).observe_scent(obs_scent, barriers)

    def get_legal_mask(
        self,
        own_position: tuple[int, int],
        barriers: list[tuple[int, int]],
        barriers_remaining: int = 0,
    ):
        """Get legal action mask for current role."""
        from agent.rl.action_space import compute_legal_mask_cop, compute_legal_mask_thief

        if self.role == "cop":
            return compute_legal_mask_cop(
                own_position, barriers, barriers_remaining, self.grid_size
            )
        else:
            return compute_legal_mask_thief(own_position, barriers, self.grid_size)

    def get_action_names(self) -> list[str]:
        from agent.rl.action_space import COP_ACTIONS, THIEF_ACTIONS

        return COP_ACTIONS if self.role == "cop" else THIEF_ACTIONS

    def select_move_heuristic(
        self,
        own_position: tuple[int, int],
        barriers: list[tuple[int, int]],
        barriers_remaining: int = 0,
    ) -> str:
        """Heuristic fallback — never used in counted mode."""
        import numpy as np

        from agent.rl.heuristics import evasion_thief, pursuit_cop

        belief = self.belief_engine.belief
        centroid = tuple(int(x) for x in np.unravel_index(belief.prob.argmax(), belief.prob.shape))
        if self.role == "cop":
            return pursuit_cop(own_position, centroid, barriers, barriers_remaining, self.grid_size)
        else:
            return evasion_thief(own_position, centroid, barriers, self.grid_size)

    def generate_hint(self, move: str, intent: str = "truth") -> str:
        """Generate free-language hint via language policy."""
        from agent.language.hint_policy import generate_hint

        return generate_hint(move, intent)

    def is_counted(self) -> bool:
        from agent.runtime_mode import RuntimeMode

        return self.mode == RuntimeMode.COUNTED
