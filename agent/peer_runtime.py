"""PeerRuntime — production peer-to-peer game runtime.

Replaces GameRunner in production. Each agent runs its own PeerRuntime;
there is no central third-party judge. Sub-modules:
  peer_runtime_io    — config loading, persistence helpers
  peer_runtime_audit — final audit and game-end notification
"""

import logging
from pathlib import Path

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
                "grid_state": gs,
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
        self.protocol_adapter = None  # set after discovery in run_game()

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
        await self._init_protocol_adapter()
        await self._send_start_game(game_id, counted_mode=effective_counted_mode)
        rules = RulesEngine(self.board, max_turns=self.max_turns)
        winner, abort_reason, final_step = await run_peer_turn_loop(self, rules, self.max_turns)

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
        """Discover opponent's MCP tools and build the protocol adapter crew."""
        try:
            from agent.mcp.discovery import ProtocolDiscovery
            from agent.mcp.protocol_adapter import ProtocolAdapterCrew

            discovery = ProtocolDiscovery(self.opponent_client.peer_url)
            ok = await discovery.discover()
            if ok and discovery.tools:
                # Strip pure utility tools so the LLM only sees action-relevant ones.
                action_tools = {
                    name: schema
                    for name, schema in discovery.tools.items()
                    if name.lower() not in self._UTILITY_TOOL_NAMES
                }
                if not action_tools:
                    action_tools = discovery.tools  # safety: keep all if nothing remains
                self.protocol_adapter = ProtocolAdapterCrew(
                    action_tools, self.opponent_client, self.llm
                )
                logger.info(
                    f"[PeerRuntime/{self.role}] Protocol adapter ready "
                    f"({len(action_tools)}/{len(discovery.tools)} tools after filtering)"
                )
            else:
                logger.warning(
                    f"[PeerRuntime/{self.role}] Discovery found no tools — direct MCP fallback"
                )
        except Exception as exc:
            logger.warning(f"[PeerRuntime/{self.role}] Protocol adapter init failed: {exc}")
            self.protocol_adapter = None

    def _init_llm(self, llm_dict: dict | None):
        try:
            from agent.llm import LLMFactory

            return (
                LLMFactory.create_from_dict(llm_dict) if llm_dict else LLMFactory.create_from_env()
            )
        except Exception as exc:
            logger.warning(f"[PeerRuntime/{self.role}] LLM init failed: {exc}")
            return None
