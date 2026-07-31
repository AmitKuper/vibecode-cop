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


class PeerRuntime:
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
        self.opponent_client = GameMCPClient(opponent_url, secret)
        cop_start, thief_start = _load_start_positions()
        self.game_id: str = ""
        self.game_dir: Path = Path(".")
        self.board: Board = Board(cop_position=cop_start, thief_position=thief_start)
        self._my_commits: dict[int, dict] = {}

    async def run_game(self, game_id: str) -> dict:
        """Drive this agent's side of the game to completion."""
        self.game_id = game_id
        self.game_dir = self.games_dir / game_id
        self.game_dir.mkdir(parents=True, exist_ok=True)
        cop_start, thief_start = _load_start_positions()
        self.board = Board(cop_position=cop_start, thief_position=thief_start)
        self._my_commits = {}
        created_at = _now()
        save_game_state(self.game_dir, {"step": 0, "turn": 0, "completed": False,
                                        "winner": None, "created_at": created_at})
        logger.info(f"[PeerRuntime/{self.role}] Starting game {game_id}")
        rules = RulesEngine(self.board, max_turns=self.max_turns)
        winner, abort_reason, final_step = await run_peer_turn_loop(self, rules, self.max_turns)

        audit_ok, audit_details = await do_final_audit(
            self.opponent_client, game_id, self.role, self.config_sha256,
            self._my_commits, self.game_dir, self.opponent_role, final_step, _now,
        )
        if not audit_ok:
            winner = "TECHNICAL_LOSS"
            abort_reason = "commitment_mismatch"
            logger.warning(f"[PeerRuntime/{self.role}] Audit failed — overriding winner")

        ended_at = _now()
        final_state = {
            "step": self.board.turn, "turn": self.board.turn,
            "cop_position": self.board.cop_position,
            "thief_position": self.board.thief_position,
            "move_history": self.board.move_history,
            "completed": True, "winner": winner, "abort_reason": abort_reason,
            "created_at": created_at, "ended_at": ended_at, "final_step": final_step,
            "audit_ok": audit_ok, "audit_details": audit_details,
        }
        save_game_state(self.game_dir, final_state)
        write_result(
            self.game_dir, game_id, self.role, self.config_sha256, self.group_name,
            self.board, final_state, final_step, audit_ok,
            self._my_commits, count_opponent_commits(self.game_dir),
        )
        await notify_game_end(
            self.opponent_client, game_id, self.role, self.config_sha256,
            final_step, winner or "unknown", _now,
        )
        result = {"ok": True, "game_id": game_id, "role": self.role,
                  "winner": winner, "final_step": final_step,
                  "abort_reason": abort_reason, "audit_ok": audit_ok}
        logger.info(f"[PeerRuntime/{self.role}] Game {game_id} done: {result}")
        return result

    def _store_my_commit(self, step: int, payload: dict) -> None:
        self._my_commits[step] = payload
        store_commit(self.game_dir, self.role, step, payload)

    def _build_observation(self, game_state: dict) -> dict:
        """Build a partial observation dict (hidden-info compliant)."""
        if self.role == "cop":
            return {"my_position": game_state.get("cop_position", [0, 0]),
                    "scent_field": game_state.get("scent_field", []),
                    "turn": game_state.get("turn", 0)}
        return {"my_position": game_state.get("thief_position", [6, 6]),
                "turn": game_state.get("turn", 0)}

    def _select_move_rl(self, observation: dict) -> str | None:
        """Hook for RL/strategy move selection. Returns None to use heuristic."""
        return None
