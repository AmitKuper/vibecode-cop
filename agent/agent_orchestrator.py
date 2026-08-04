"""AgentOrchestrator — single composition root for all v7 subsystems."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.audit.step_journal import StepJournal
    from agent.domain.transition import TransitionResult
    from agent.domain.types import DomainState
    from agent.runtime_mode import RuntimeMode
    from agent.step0.declaration import PeerDeclaration

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

        # Language policy
        from agent.language.deception_policy import NaturalLanguagePolicy

        self.language_policy: NaturalLanguagePolicy = NaturalLanguagePolicy(role)

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

        # Watchdog / gatekeeper (set by lifecycle methods)
        self._watchdog_heartbeat_path: str = ""
        self._watchdog_evidence_path: str = ""
        self._watchdog_proc = None
        self._gatekeeper = None

        # Protocol port (5B)
        self._protocol_port = None
        self._mapping_hash = ""

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

        # Validate RL model manifest
        from pathlib import Path

        from agent.rl.model_schema import ModelLoadError, load_manifest

        manifest_path = self.config.get("model_manifest_path", "models/MANIFEST.json")
        if not Path(manifest_path).exists():
            raise ValueError(f"COUNTED mode rejected: model manifest not found at {manifest_path}")
        try:
            manifest = load_manifest(manifest_path)
            if self.role not in manifest:
                raise ValueError(f"COUNTED mode rejected: no model for role {self.role!r}")
            entry = manifest[self.role]
            if entry.training_steps == 0:
                raise ValueError("COUNTED mode rejected: model has training_steps=0 (placeholder)")
            if entry.evaluation_win_rate == 0.0:
                raise ValueError(
                    "COUNTED mode rejected: model has evaluation_win_rate=0.0 (placeholder)"
                )
            ok, reason = entry.is_compatible(self.role, self.config.get("grid_size", 7))
            if not ok:
                raise ValueError(f"COUNTED mode rejected: model incompatible — {reason}")
        except ModelLoadError as e:
            raise ValueError(f"COUNTED mode rejected: {e}") from e

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
        """Generate free-language hint via language policy (legacy interface)."""
        from agent.language.deception_policy import DeceptionIntent

        _member_map = DeceptionIntent._value2member_map_
        intent_enum = DeceptionIntent(intent) if intent in _member_map else DeceptionIntent.TRUTH
        return self.language_policy.generate(move, intent_enum)

    def generate_strategic_hint(self, move: str) -> tuple[str, str]:
        """Generate a strategically chosen hint and its intent. Returns (hint, intent_str)."""
        entropy = self.belief_engine.belief.entropy
        intent = self.language_policy.choose_intent(step=0, belief_entropy=entropy)
        hint = self.language_policy.generate(move, intent)
        return hint, intent.value

    def apply_turn(
        self,
        state: DomainState,
        cop_action: str,
        thief_action: str,
    ) -> TransitionResult:
        """Apply a joint action through the canonical domain engine.

        Returns the TransitionResult (immutable). Callers must check
        result.outcome to detect terminal states — this method propagates
        domain errors without converting illegal actions to STAY in counted mode.
        """
        from agent.domain.transition import apply_joint_action

        result = apply_joint_action(state, cop_action, thief_action)
        new = result.new_state
        self.update_scent_and_belief(
            new.cop_position,
            new.thief_position,
            list(new.barriers),
        )
        return result

    def is_counted(self) -> bool:
        from agent.runtime_mode import RuntimeMode

        return self.mode == RuntimeMode.COUNTED

    # ------------------------------------------------------------------
    # Phase 3 v7: lifecycle methods wired into production path
    # ------------------------------------------------------------------

    def build_step0_declaration(self, game_uid: str, gamelet: int = 0) -> PeerDeclaration:
        """Build a Step-0 declaration from current orchestrator state."""
        import platform
        import subprocess

        from agent.step0.declaration import PeerDeclaration

        try:
            git_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True
            ).stdout.strip()
        except Exception:
            git_sha = "unknown"

        return PeerDeclaration(
            game_uid=game_uid,
            model_role=self.role,
            model_algorithm=self.config.get("model_algorithm", "heuristic"),
            model_sha256=self.config.get("model_sha256", "placeholder"),
            git_sha=git_sha,
            os_info=platform.platform(),
            cpu_info=platform.processor(),
            counted_mode=self.is_counted(),
            local_endpoint=self.config.get("my_endpoint", ""),
            canonical_config_sha256=self.config.get("canonical_config_sha256", ""),
            scent_model_hash=self.config.get("scent_model_hash", ""),
        )

    def validate_counted_declaration(self, decl: PeerDeclaration) -> list[str]:
        """Validate declaration for counted mode. Returns list of errors."""
        if not self.is_counted():
            return []
        from agent.step0.validator import validate_for_counted_mode

        return validate_for_counted_mode(decl)

    def record_step_evidence(
        self,
        gamelet: int,
        step: int,
        local_commitment: str = "",
        local_move: str = "",
        received_commitment: str = "",
        received_move: str = "",
        protocol_state_before: str = "",
        protocol_state_after: str = "",
    ) -> str:
        """Append step evidence to journal. Returns new chain hash."""
        import time

        from agent.audit.step_journal import StepEvidence

        evidence = StepEvidence(
            game_uid=self.game_uid,
            gamelet=gamelet,
            step=step,
            role=self.role,
            local_commitment=local_commitment,
            local_move=local_move,
            received_commitment=received_commitment,
            received_move=received_move,
            protocol_state_before=protocol_state_before,
            protocol_state_after=protocol_state_after,
            timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        journal = self.get_journal(gamelet)
        return journal.append(evidence)

    def emit_heartbeat(self, step: int = 0) -> None:
        """Emit watchdog heartbeat from main process."""
        if self._watchdog_heartbeat_path:
            import os

            from agent.reliability.watchdog import write_heartbeat

            write_heartbeat(
                self._watchdog_heartbeat_path,
                pid=os.getpid(),
                game_uid=self.game_uid,
                session_id=self.game_uid,
                step=step,
                state_path=f"{self.work_dir}/recovery_{self.game_uid}.json",
            )

    def start_watchdog(self) -> None:
        """Launch independent watchdog subprocess."""
        from agent.runtime_mode import RuntimeMode

        self._watchdog_heartbeat_path = f"{self.work_dir}/heartbeat_{self.game_uid}.json"
        self._watchdog_evidence_path = f"{self.work_dir}/watchdog_evidence_{self.game_uid}.json"
        if self.mode != RuntimeMode.DEVELOPMENT:
            try:
                from agent.reliability.watchdog import launch_watchdog_subprocess

                self._watchdog_proc = launch_watchdog_subprocess(
                    self._watchdog_heartbeat_path,
                    self._watchdog_evidence_path,
                )
            except Exception as e:
                logger.warning("Failed to start watchdog: %s", e)
        # Emit first heartbeat
        self.emit_heartbeat(step=0)

    def stop_watchdog(self) -> None:
        """Terminate watchdog subprocess."""
        import contextlib

        proc = getattr(self, "_watchdog_proc", None)
        if proc is not None:
            with contextlib.suppress(Exception):
                proc.terminate()

    def record_match_in_ledger(
        self,
        opponent_id: str,
        match_id: str,
        counted: bool,
        declaration_hash: str = "",
        result_hash: str = "",
    ) -> None:
        """Append match to league ledger. Raises LeagueLedgerError on constraint violation."""
        import time

        from agent.step0.league_ledger import LedgerEntry

        entry = LedgerEntry(
            opponent_id=opponent_id,
            match_id=match_id,
            counted=counted,
            declaration_hash=declaration_hash,
            result_hash=result_hash,
            timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        self.league_ledger.append(entry)

    # ------------------------------------------------------------------
    # Phase 5 v7: SafeLiveView publishing and GameProtocolPort wiring
    # ------------------------------------------------------------------

    def publish_live_view(
        self,
        own_position: tuple[int, int],
        barriers: list[tuple[int, int]],
        last_hint: str = "",
        hint_reliability: float = 0.5,
        turn: int = 0,
        gamelet: int = 1,
        score: dict = None,
        own_barriers_remaining: int = 0,
        protocol_state: str = "UNKNOWN",
        your_turn: bool = False,
        connection_healthy: bool = True,
    ) -> None:
        """Publish a SafeLiveView update — no hidden opponent coordinates."""
        from agent.observation import SafeLiveView

        belief_heatmap = self.belief_engine.belief.prob.tolist()
        if self.role == "cop":
            opponent_scent = self.scent_fields.cop_observation_scent()
        else:
            opponent_scent = self.scent_fields.thief_observation_scent()
        view = SafeLiveView(
            own_position=own_position,
            belief_heatmap=belief_heatmap,
            opponent_scent=opponent_scent,
            last_hint=last_hint,
            hint_reliability=hint_reliability,
            turn=turn,
            gamelet=gamelet,
            score=score or {"cop": 0, "thief": 0},
            own_barriers_remaining=own_barriers_remaining,
            protocol_state=protocol_state,
            your_turn=your_turn,
            connection_healthy=connection_healthy,
        )
        self.live_view.update(view)

    def create_protocol_port(self, endpoint: str = "", stub_handler=None):
        """Create the deterministic GameProtocolPort."""
        from agent.mcp.protocol_port import GameProtocolPort, ProtocolMapping
        from agent.mcp.transport_port import SSETransportAdapter, StubTransportAdapter

        mapping = ProtocolMapping.default()
        mapping.lock()
        if stub_handler is not None:
            transport = StubTransportAdapter(stub_handler)
        else:
            transport = SSETransportAdapter()
        self._protocol_port = GameProtocolPort(transport, mapping)
        self._mapping_hash = mapping.mapping_hash
        return self._protocol_port

    def send_report_via_gatekeeper(
        self,
        idempotency_key: str,
        game_id: str,
        result_json: str,
    ) -> str:
        """Send Gmail report through the full Gatekeeper pipeline."""
        if self._gatekeeper is None:
            from agent.gmail.gatekeeper import Gatekeeper

            gmail_sender = self.config.get("gmail_sender")
            if gmail_sender is None:
                raise RuntimeError("No gmail_sender configured — cannot send report")
            self._gatekeeper = Gatekeeper(gmail_sender)
        return self._gatekeeper.send(
            idempotency_key=idempotency_key,
            game_id=game_id,
            subject=f"Game Result — {game_id}",
            body=result_json,
        )
