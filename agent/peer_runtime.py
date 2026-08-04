"""PeerRuntime — production peer-to-peer game runtime.

Replaces GameRunner in production. Each agent runs its own PeerRuntime;
there is no central third-party judge. Sub-modules:
  peer_runtime_io    — config loading, persistence helpers
  peer_runtime_audit — final audit and game-end notification
"""

import hashlib
import json
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
        self.opponent_client = GameMCPClient(opponent_url, secret)
        cop_start, thief_start = _load_start_positions()
        self.game_id: str = ""
        self.game_dir: Path = Path(".")
        self.board: Board = Board(cop_position=cop_start, thief_position=thief_start)
        self._my_commits: dict[int, dict] = {}
        self._cop_barriers_remaining: int = 14  # reset per game in run_game()
        self.llm = self._init_llm(llm_dict)
        self.crews: dict = {}
        self.protocol_adapter = None  # set after adaptive negotiation in run_game()
        self._adaptive_profile = None  # ProtocolProfile set after negotiation
        self.orchestrator: AgentOrchestrator | None = None  # lazy-init in run_game()

    async def run_game(self, game_id: str, counted_mode: bool | None = None) -> dict:
        """Drive this agent's side of the game to completion.

        Args:
            game_id: Unique game identifier in '<uuid>_g<N>' format.
            counted_mode: If True, a failed handshake raises RuntimeError instead of
                continuing.  Defaults to self.counted_mode set at construction time.
        """
        effective_counted_mode = counted_mode if counted_mode is not None else self.counted_mode
        self.game_id = game_id
        self.game_dir = self.games_dir / game_id

        # Initialize AgentOrchestrator (v7 composition root) on first game
        if self.orchestrator is None:
            from agent.agent_orchestrator import AgentOrchestrator
            from agent.runtime_mode import RuntimeMode

            _mode = RuntimeMode.COUNTED if effective_counted_mode else RuntimeMode.DEVELOPMENT
            try:
                self.orchestrator = AgentOrchestrator(
                    role=self.role,
                    game_uid=game_id,
                    grid_size=self.config.get("grid_size", 7) if hasattr(self, "config") else 7,
                    mode=_mode,
                )
            except Exception as _orch_err:
                logger.warning(
                    "[PeerRuntime/%s] AgentOrchestrator init failed: %s", self.role, _orch_err
                )

        self.game_dir.mkdir(parents=True, exist_ok=True)
        cop_start, thief_start = _load_start_positions()
        self.board = Board(cop_position=cop_start, thief_position=thief_start)
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
        )
        if not audit_ok:
            winner = "TECHNICAL_LOSS"
            abort_reason = "commitment_mismatch"
            logger.warning(f"[PeerRuntime/{self.role}] Audit failed — overriding winner")

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
        )
        await notify_game_end(
            self.opponent_client,
            game_id,
            self.role,
            self.config_sha256,
            final_step,
            winner or "unknown",
            _now,
        )
        # Fix 3: Cleanup session from registry after terminal state
        get_coordinator().cleanup_session(game_id, gamelet, self.role)

        result = {
            "ok": True,
            "game_id": game_id,
            "role": self.role,
            "winner": winner,
            "final_step": final_step,
            "abort_reason": abort_reason,
            "audit_ok": audit_ok,
        }

        # Phase 3 v8: Wire LeagueLedger into counted mode terminal state
        if effective_counted_mode and self.orchestrator is not None:
            try:
                result_hash = hashlib.sha256(
                    json.dumps(result, sort_keys=True, default=str).encode()
                ).hexdigest()
                self.orchestrator.record_match_in_ledger(
                    opponent_id=game_id.split("_")[0] if "_" in game_id else game_id,
                    match_id=game_id,
                    counted=True,
                    result_hash=result_hash,
                )
                logger.info(
                    "[PeerRuntime/%s] Match recorded in league ledger: %s",
                    self.role, game_id,
                )
            except Exception as _ledger_err:
                logger.warning(
                    "[PeerRuntime/%s] LeagueLedger record failed: %s",
                    self.role, _ledger_err,
                )

        # Phase 3 v8: Wire Gatekeeper into counted mode terminal state (each peer sends report)
        if effective_counted_mode and audit_ok and self.orchestrator is not None:
            try:
                _result_json = json.dumps(result, sort_keys=True, default=str)
                self.orchestrator.send_report_via_gatekeeper(
                    idempotency_key=f"{game_id}_{self.role}",
                    game_id=game_id,
                    result_json=_result_json,
                )
                logger.info("[PeerRuntime/%s] Gmail report sent via Gatekeeper", self.role)
            except Exception as _gk_err:
                logger.warning(
                    "[PeerRuntime/%s] Gatekeeper send failed: %s", self.role, _gk_err
                )

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
        # 3C: Wire Step-0 validation into counted mode startup
        if counted_mode and self.orchestrator is not None:
            decl = self.orchestrator.build_step0_declaration(game_id)
            # Attach adaptive protocol profile hash if negotiation succeeded
            if self._adaptive_profile is not None:
                decl.adapter_mapping_hash = self._adaptive_profile.profile_hash
                decl.transport = self._adaptive_profile.remote_transport
            errors = self.orchestrator.validate_counted_declaration(decl)
            if errors:
                raise RuntimeError(f"Step-0 validation failed for counted mode: {errors}")

        from agent.mcp.messages import StartGameMessage

        gamelet = gamelet_from_game_id(game_id)
        msg = StartGameMessage(
            game_id=game_id,
            roles={"cop": self.group_name, "thief": "opponent"},
            config_sha256=self.config_sha256,
            protocol_version="1.0",
            endpoint=self.my_endpoint,
            timestamp=_now(),
        )
        try:
            resp = await self.opponent_client.start_game(msg)
            if resp.get("ok"):
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
        self._my_commits[step] = payload
        store_commit(self.game_dir, self.role, step, payload)

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
        try:
            from agent.adaptive.pipeline import native_adapter, run_adaptive_negotiation

            opponent_base = self.opponent_client.peer_url.rstrip("/mcp").rstrip("/")
            result = await run_adaptive_negotiation(
                opponent_url=opponent_base,
                llm=self.llm,
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
            logger.warning(
                "[PeerRuntime/%s] Adaptive negotiation failed (%s) — using native identity adapter",
                self.role, exc,
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
