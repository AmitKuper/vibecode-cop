"""PeerRuntime — production peer-to-peer game runtime.

Replaces GameRunner in production. Each agent runs its own PeerRuntime;
there is no central third-party judge. Sub-modules:
  peer_runtime_io    — config loading, persistence helpers
  peer_runtime_audit — final audit and game-end notification
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.agent_orchestrator import AgentOrchestrator

from agent.board import Board
from agent.mcp.client import GameMCPClient
from agent.mcp.coordinator import gamelet_from_game_id, get_coordinator
from agent.peer_runtime_audit import count_opponent_commits, do_final_audit, notify_game_end
from agent.peer_runtime_io import (
    _load_start_positions,
    _now,
    save_game_state,
    store_commit,
    write_result,
)
from agent.peer_turn_loop import run_peer_turn_loop
from agent.rules_engine import RulesEngine

logger = logging.getLogger(__name__)

try:
    from agent.orchestrator_crew import CrewMixin as _CrewMixin
except Exception as _crew_import_err:
    logger.warning(f"CrewMixin unavailable ({_crew_import_err}); RL/LLM selection disabled")

    class _CrewMixin:  # type: ignore[no-redef]
        def _select_move_rl(self, obs):
            return None

        def _select_move_llm(self, game_id, obs):
            raise RuntimeError("crewai unavailable")

        def _build_observation(self, gs):
            role = getattr(self, "role", "cop")
            pos = (
                gs.get("cop_position", [0, 0])
                if role == "cop"
                else gs.get("thief_position", [3, 3])
            )
            return {
                "own_position": pos,
                "turn": gs.get("turn", 0),
                "scent_field": gs.get("scent_field", []),
                "candidate_actions": [],
            }

        def _short_move(self, long):
            return {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W", "STAY": "STAY"}.get(
                long, long
            )

        def _long_move(self, short):
            return {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST", "STAY": "STAY"}.get(
                short, short
            )


class PeerRuntime(_CrewMixin):
    """Production peer-to-peer runtime for one agent side of the game."""

    def __init__(
        self,
        role: str,
        secret: str,
        config_sha256: str,
        opponent_url: str,
        games_dir: Path | str = Path("agent/memory"),
        max_turns: int = 35,
        group_name: str = "unknown",
        llm_dict: dict | None = None,
        my_endpoint: str = "",
        counted_mode: bool = False,
        orchestrator_config: dict | None = None,
    ):
        if role not in ("cop", "thief"):
            raise ValueError(f"role must be 'cop' or 'thief', got {role!r}")
        self.role = role
        self.opponent_role = "thief" if role == "cop" else "cop"
        self.secret = secret
        self.config_sha256 = config_sha256
        self.max_turns = max_turns
        self.group_name = group_name
        self.games_dir = Path(games_dir)
        self.my_endpoint = my_endpoint or "http://localhost:5000/mcp"
        self.counted_mode = counted_mode
        self.orchestrator_config = dict(orchestrator_config or {})
        from agent.config.shared_config import load_shared_config
        from agent.domain.config_validator import game_config_from_dict
        from agent.domain.types import DomainState

        shared_config = self.orchestrator_config.get("shared_config") or load_shared_config()
        self.game_config = game_config_from_dict(shared_config)
        if self.counted_mode:
            self.max_turns = self.game_config.max_moves
        self.opponent_client = GameMCPClient(opponent_url, secret)
        cop_start, thief_start = _load_start_positions()
        self.game_id: str = ""
        self.game_dir: Path = Path(".")
        self.board: Board = Board(cop_position=cop_start, thief_position=thief_start)
        self._domain_state = DomainState.from_board(self.board)
        self._last_transition_result = None
        self._public_transition_root = ""
        self._my_commits: dict[int, dict] = {}
        self._cop_barriers_remaining: int = 14  # reset per game in run_game()
        self.llm = self._init_llm(llm_dict)
        self.crews: dict = {}
        self.protocol_adapter = None  # set after adaptive negotiation in run_game()
        self._adaptive_profile = None  # ProtocolProfile set after negotiation
        self.orchestrator: AgentOrchestrator | None = None  # lazy-init in run_game()
        self.rl_model_loaded = False
        self._last_opponent_hint = ""
        from agent.step0.signing import generate_key_pair

        self._signing_private_key, self._signing_public_key = generate_key_pair()
        self._signing_key_id = hashlib.sha256(self._signing_public_key).hexdigest()[:16]
        self._inbound_profile_hash = hashlib.sha256(
            b"course-p2p-signed-envelope-response-v1"
        ).hexdigest()
        self._local_step0: dict = {}
        self._remote_step0: dict = {}
        self._step0_agreements: dict = {}
        self._local_audit_summaries: dict = {}
        self._remote_audit_summaries: dict = {}
        self._observed_gamelet_outcomes: dict[str, dict] = {}

    def _gamelet_number(self, game_id: str) -> int:
        """Parse and enforce the counted six-gamelet API boundary."""
        gamelet = gamelet_from_game_id(game_id, strict=self.counted_mode)
        if self.counted_mode and gamelet not in range(1, 7):
            raise ValueError(f"COUNTED gamelet must be in 1..6, got {gamelet}")
        return gamelet

    def _ensure_orchestrator(self, game_id: str) -> AgentOrchestrator | None:
        """Construct the sole composition root, failing closed in counted mode."""
        if self.orchestrator is not None:
            return self.orchestrator
        from agent.agent_orchestrator import AgentOrchestrator
        from agent.runtime_mode import RuntimeMode

        mode = RuntimeMode.COUNTED if self.counted_mode else RuntimeMode.DEVELOPMENT
        try:
            self.orchestrator = AgentOrchestrator(
                role=self.role,
                game_uid=game_id,
                grid_size=int(self.orchestrator_config.get("grid_size", 7)),
                mode=mode,
                work_dir=str(self.games_dir / game_id),
                config=self.orchestrator_config,
            )
            self.rl_model_loaded = getattr(self.orchestrator, "movement_policy", None) is not None
        except Exception as exc:
            if self.counted_mode:
                raise RuntimeError(
                    f"COUNTED AgentOrchestrator initialization failed: {exc}"
                ) from exc
            logger.warning("AgentOrchestrator initialization failed: %s", exc)
        return self.orchestrator

    def reset_for_new_series(self) -> None:
        """Clear per-series adaptive profile so the next series renegotiates cleanly.

        Call this before the first gamelet of a new series. Safe to call even if
        the previous series completed normally — resets both sides of the profile pair
        so _init_protocol_adapter() starts fresh instead of hitting the
        'incomplete adaptive profile state cannot be reused' guard.
        """
        self.protocol_adapter = None
        self._adaptive_profile = None
        logger.info("[PeerRuntime/%s] Adaptive profile cleared for new series", self.role)

    async def run_game(self, game_id: str, counted_mode: bool | None = None) -> dict:
        """Drive this agent's side of the game to completion.

        Args:
            game_id: Unique game identifier in '<uuid>_g<N>' format.
            counted_mode: If True, a failed handshake raises RuntimeError instead of
                continuing.  Defaults to self.counted_mode set at construction time.
        """
        effective_counted_mode = counted_mode if counted_mode is not None else self.counted_mode
        self._gamelet_number(game_id)
        self.game_id = game_id
        self.game_dir = self.games_dir / game_id

        if effective_counted_mode != self.counted_mode:
            raise RuntimeError("Runtime mode cannot change after PeerRuntime construction")
        self._ensure_orchestrator(game_id)
        if self.orchestrator is not None:
            self.orchestrator.game_uid = game_id
        if hasattr(self.orchestrator, "reset_movement_history"):
            self.orchestrator.reset_movement_history()
        self._last_opponent_hint = ""

        self.game_dir.mkdir(parents=True, exist_ok=True)
        cop_start, thief_start = _load_start_positions()
        self.board = Board(cop_position=cop_start, thief_position=thief_start)
        from agent.domain.types import DomainState

        self._domain_state = DomainState.from_board(self.board)
        self._last_transition_result = None
        self._public_transition_root = ""
        self._my_commits = {}
        self._cop_barriers_remaining = 14
        created_at = _now()
        save_game_state(
            self.game_dir,
            {"step": 0, "turn": 0, "completed": False, "winner": None, "created_at": created_at},
        )
        logger.info(f"[PeerRuntime/{self.role}] Starting game {game_id}")

        # 3A/3B: Start watchdog before gameplay
        if self.orchestrator is not None:
            self.orchestrator.start_watchdog()

        try:
            await self._init_protocol_adapter()
            await self._send_start_game(game_id, counted_mode=effective_counted_mode)
            rules = RulesEngine(self.board, max_turns=self.max_turns)
            winner, abort_reason, final_step = await run_peer_turn_loop(self, rules, self.max_turns)
        finally:
            # 3B: Stop watchdog after gameplay
            if self.orchestrator is not None:
                self.orchestrator.stop_watchdog()

        gamelet = gamelet_from_game_id(game_id)
        if abort_reason is not None:
            # Turn loop aborted before normal game end — sending final_audit would violate
            # the opponent's SM (it may still be in BOTH_COMMITTED or REVEAL_RECEIVED).
            audit_ok = False
            audit_details = {"error": abort_reason, "audit_status": "SKIPPED"}
            if winner is None:
                winner = "TECHNICAL_LOSS"
            logger.warning(
                "[PeerRuntime/%s] Skipping final_audit — turn loop aborted: %s",
                self.role,
                abort_reason,
            )
        else:
            audit_ok, audit_details = await do_final_audit(
                self.opponent_client,
                game_id,
                self.role,
                self.config_sha256,
                self._my_commits,
                self.game_dir,
                self.opponent_role,
                final_step,
                _now,
                gamelet=gamelet,
                runtime=self,
            )
            if not audit_ok:
                winner = "TECHNICAL_LOSS"
                abort_reason = "commitment_mismatch"
                logger.warning(f"[PeerRuntime/{self.role}] Audit failed — overriding winner")

        transition = self._last_transition_result
        if audit_ok and transition is not None and transition.outcome.value != "ongoing":
            cop_score = transition.cop_score
            thief_score = transition.thief_score
        elif audit_ok and not self.counted_mode and winner == "thief":
            cop_score = self.game_config.scoring.survival_cop
            thief_score = self.game_config.scoring.survival_thief
        else:
            cop_score = thief_score = 0

        ended_at = _now()
        final_state = {
            "step": self.board.turn,
            "turn": self.board.turn,
            "cop_position": self.board.cop_position,
            "thief_position": self.board.thief_position,
            "move_history": self.board.move_history,
            "completed": True,
            "winner": winner,
            "abort_reason": abort_reason,
            "created_at": created_at,
            "ended_at": ended_at,
            "final_step": final_step,
            "audit_ok": audit_ok,
            "cop_score": cop_score,
            "thief_score": thief_score,
            "audit_details": audit_details,
        }
        save_game_state(self.game_dir, final_state)
        write_result(
            self.game_dir,
            game_id,
            self.role,
            self.config_sha256,
            self.group_name,
            self.board,
            final_state,
            final_step,
            audit_ok,
            self._my_commits,
            count_opponent_commits(self.game_dir),
            my_endpoint=self.my_endpoint,
            opponent_group_id=getattr(self, "_opponent_group_id", ""),
            token_counts=getattr(self, "_token_counts", None),
        )
        await notify_game_end(
            self.opponent_client,
            game_id,
            self.role,
            self.config_sha256,
            final_step,
            winner or "unknown",
            _now,
            runtime=self,
        )
        result = {
            "ok": True,
            "game_id": game_id,
            "role": self.role,
            "winner": winner,
            "final_step": final_step,
            "abort_reason": abort_reason,
            "audit_ok": audit_ok,
            "cop_score": cop_score,
            "thief_score": thief_score,
        }

        logger.info(f"[PeerRuntime/{self.role}] Game {game_id} done: {result}")
        return result

    async def _send_start_game(self, game_id: str, *, counted_mode: bool = False) -> None:
        """Send start_game handshake to opponent and advance local SM to READY.

        This is mandatory before the first COMMIT.  In counted_mode the method
        raises RuntimeError on rejection or network failure so the caller can
        abort the game cleanly.  In non-counted mode the failure is logged as a
        warning and gameplay continues (the turn loop will detect the ordering
        violation at the first COMMIT).
        """
        self._ensure_orchestrator(game_id)
        from agent.peer_step0 import (
            Step0ExchangeError,
            accept_remote_signed_declaration,
            build_local_signed_declaration,
            persist_step0_evidence,
        )

        gamelet = gamelet_from_game_id(game_id)
        if counted_mode:
            preliminary = self.orchestrator.build_step0_declaration(game_id, gamelet)
            errors = self.orchestrator.validate_counted_declaration(preliminary)
            if errors:
                raise RuntimeError(f"Step-0 validation failed for counted mode: {errors}")
        local_signed = build_local_signed_declaration(self, game_id)

        from agent.mcp.messages import StartGameMessage

        msg = StartGameMessage(
            game_id=game_id,
            roles={"cop": self.group_name, "thief": "opponent"},
            config_sha256=self.config_sha256,
            protocol_version="1.0",
            endpoint=self.my_endpoint,
            timestamp=_now(),
            signed_declaration=local_signed.to_dict(),
        )
        try:
            if self.protocol_adapter is not None:
                from agent.peer_turn_helpers import _call_adapted_phase

                msg_dict = msg.to_dict()
                try:
                    resp = await _call_adapted_phase(
                        self,
                        "start_game",
                        msg_dict,
                        {
                            **msg_dict,
                            "phase": "start_game",
                            "role": self.role,
                            "gamelet": gamelet,
                        },
                    )
                except Exception as adapter_exc:
                    if counted_mode:
                        raise RuntimeError(
                            f"[PeerRuntime/{self.role}] start_game adapter failed: {adapter_exc}"
                        ) from adapter_exc
                    logger.warning(
                        "[PeerRuntime/%s] start_game adapter failed (%s) — clearing adapter, "
                        "retrying with native client",
                        self.role,
                        adapter_exc,
                    )
                    self.protocol_adapter = None
                    self._adaptive_profile = None
                    resp = await self.opponent_client.start_game(msg)
                if not resp.get("ok") and self.protocol_adapter is not None:
                    logger.warning(
                        "[PeerRuntime/%s] start_game adapter returned non-ok — clearing adapter, "
                        "retrying with native client",
                        self.role,
                    )
                    self.protocol_adapter = None
                    self._adaptive_profile = None
                    resp = await self.opponent_client.start_game(msg)
            else:
                resp = await self.opponent_client.start_game(msg)
            if resp.get("ok"):
                try:
                    agreement = accept_remote_signed_declaration(
                        self, game_id, resp.get("signed_declaration")
                    )
                    remote_hash = resp.get("declaration_agreement_hash")
                    if remote_hash and remote_hash != agreement.agreement_hash:
                        raise Step0ExchangeError("bilateral declaration agreement hash mismatch")
                    persist_step0_evidence(self, game_id)
                except Step0ExchangeError:
                    if counted_mode:
                        raise
                    logger.warning(
                        "[PeerRuntime/%s] Development peer omitted/failed signed Step-0",
                        self.role,
                    )
                get_coordinator().on_handshake_complete(game_id, gamelet, self.role)
                logger.info(
                    f"[PeerRuntime/{self.role}] start_game handshake complete for {game_id}"
                )
            else:
                msg_text = f"[PeerRuntime/{self.role}] start_game rejected by opponent: {resp}"
                if counted_mode:
                    raise RuntimeError(msg_text)
                logger.warning(msg_text)
        except RuntimeError as exc:
            if counted_mode:
                raise
            logger.warning(
                f"[PeerRuntime/{self.role}] start_game failed: {exc} "
                "— proceeding without confirmed handshake"
            )
        except Exception as exc:
            msg_text = (
                f"[PeerRuntime/{self.role}] start_game send failed: {exc} "
                "— proceeding without confirmed handshake"
            )
            if counted_mode:
                raise RuntimeError(msg_text) from exc
            logger.warning(msg_text)

    def _store_my_commit(self, step: int, payload: dict) -> None:
        try:
            store_commit(self.game_dir, self.role, step, payload)
        except Exception:
            if self.counted_mode:
                self.declare_technical_loss(
                    f"commitment persistence failed at step {step}",
                    subsystem="commitment_store",
                    step=step,
                )
            raise
        self._my_commits[step] = payload

    def declare_technical_loss(self, reason: str, *, subsystem: str, step: int = 0) -> None:
        """Route a counted failure through the sole coordinator and durable evidence."""
        gamelet = max(1, gamelet_from_game_id(self.game_id))
        get_coordinator().on_technical_loss(
            self.game_id,
            gamelet,
            self.role,
            reason=reason,
            evidence={"subsystem": subsystem, "step": step},
            evidence_path=str(self.game_dir / "technical_loss.json"),
        )

    def persist_recovery_state(self, step: int) -> None:
        """Persist the minimal private state needed for controlled crash recovery."""
        if self.orchestrator is None:
            if self.counted_mode:
                raise RuntimeError("counted recovery store is unavailable")
            return
        import time

        from agent.reliability.recovery_state import RecoveryState

        gamelet = max(1, gamelet_from_game_id(self.game_id))
        coordinator = get_coordinator()
        protocol_state = coordinator.get_state(self.game_id, gamelet, self.role)
        journal = self.orchestrator.get_journal(gamelet)
        state = RecoveryState(
            game_uid=self.game_id,
            session_id=self.game_id,
            role=self.role,
            sm_state=protocol_state.value if protocol_state is not None else "UNKNOWN",
            expected_step=step + 1,
            last_accepted_commit_step=step,
            transcript_root=journal.transcript_root(),
            idempotency_journal=coordinator.snapshot_idempotency(self.game_id, gamelet, self.role),
            pending_request_id="",
            local_commitments={str(k): v["h_commit"] for k, v in self._my_commits.items()},
            local_nonces={str(k): v["nonce"] for k, v in self._my_commits.items()},
            report_delivered=False,
            timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        try:
            self.orchestrator.recovery_store.save(state)
        except Exception:
            if self.counted_mode:
                self.declare_technical_loss(
                    f"recovery-state persistence failed at step {step}",
                    subsystem="recovery_store",
                    step=step,
                )
            raise

    # Tool names that are not per-turn game-action tools.
    _UTILITY_TOOL_NAMES = frozenset(
        {
            "ping",
            "get_config",
            "get_protocol",
            "list_tools",
            "health",
            "status",
            "info",
            "describe",
            "start_game",  # initialisation only — never needed mid-game
        }
    )

    async def _init_protocol_adapter(self) -> None:
        """Pre-game adaptive MCP negotiation (LLM runs ONCE; no LLM per turn).

        Replaces the legacy ProtocolAdapterCrew which called an LLM on every
        turn. The new pipeline:
          TransportProbe → MCPIntrospector → ProtocolUnderstandingAgent (once)
          → StaticSemanticVerifier → ConformanceProbes → DeterministicProtocolAdapter
        """
        if self.protocol_adapter is not None and self._adaptive_profile is not None:
            from agent.adaptive.pipeline import verify_locked_schema

            await verify_locked_schema(self._adaptive_profile)
            logger.info(
                "[PeerRuntime/%s] Reusing series-locked ProtocolProfile %s",
                self.role,
                self._adaptive_profile.profile_hash,
            )
            return
        if self.protocol_adapter is not None or self._adaptive_profile is not None:
            raise RuntimeError("incomplete adaptive profile state cannot be reused")
        try:
            from agent.adaptive.pipeline import native_adapter, run_adaptive_negotiation
            from agent.adaptive.transport_probe import normalize_mcp_base_url

            opponent_base = normalize_mcp_base_url(self.opponent_client.peer_url)
            result = await run_adaptive_negotiation(
                opponent_url=opponent_base,
                llm=self.llm,
            )
            self.opponent_client.configure_transport(
                result.profile.remote_transport,
                result.profile.remote_endpoint,
                result.profile.remote_stdio_command,
            )
            self.protocol_adapter = result.adapter
            self._adaptive_profile = result.profile
            logger.info(
                "[PeerRuntime/%s] Adaptive negotiation complete: profile_hash=%s "
                "transport=%s cache_hit=%s",
                self.role,
                result.profile_hash,
                result.profile.remote_transport,
                result.cache_hit,
            )
        except Exception as exc:
            if self.counted_mode:
                self.protocol_adapter = None
                self._adaptive_profile = None
                raise RuntimeError(f"Adaptive negotiation failed in COUNTED mode: {exc}") from exc
            logger.warning(
                "[PeerRuntime/%s] Adaptive negotiation failed (%s) — using native identity adapter",
                self.role,
                exc,
            )
            from agent.adaptive.pipeline import native_adapter

            _nat = native_adapter()
            self.protocol_adapter = _nat.adapter
            self._adaptive_profile = _nat.profile

    def _init_llm(self, llm_dict: dict | None):
        try:
            from agent.llm import LLMFactory

            return (
                LLMFactory.create_from_dict(llm_dict) if llm_dict else LLMFactory.create_from_env()
            )
        except Exception as exc:
            logger.warning(f"[PeerRuntime/{self.role}] LLM init failed: {exc}")
            return None
