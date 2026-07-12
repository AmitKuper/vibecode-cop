"""PeerRuntime — production peer-to-peer game runtime.

Replaces GameRunner in production. Each agent runs its own PeerRuntime;
there is no central third-party judge. The runtime:
  1. Drives the commit-reveal turn loop for this agent's side.
  2. Verifies the opponent's commitments locally after each reveal.
  3. Runs a final audit at game end by exchanging nonces with the opponent.
  4. Writes agent-local result and commitment files.

This is called from the agent's orchestrator after receiving `start_game`
from a peer (cop/__main__.py or thief/__main__.py in production mode).
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from agent.board import Board
from agent.mcp.client import GameMCPClient
from agent.mcp.messages import ActionMessage
from agent.peer_audit import load_opponent_commits, run_final_audit
from agent.peer_turn_loop import run_peer_turn_loop
from agent.rules_engine import RulesEngine

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class PeerRuntime:
    """Production peer-to-peer runtime for one agent side of the game.

    Attributes:
        role: "cop" or "thief"
        opponent_role: "thief" or "cop"
        game_id: Active game identifier
        game_dir: Agent-local directory for this game's files
        board: Live Board instance (shared mutable state during the game)
        opponent_client: MCP client connected to the opponent's endpoint
    """

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
        """Initialize PeerRuntime.

        Args:
            role: "cop" or "thief" — this agent's role.
            secret: Shared HMAC secret agreed during negotiation.
            config_sha256: SHA-256 of the shared config (binds board, rules).
            opponent_url: Full MCP URL of the opponent (http://host:port/mcp).
            games_dir: Root directory for game data (agent-local).
            max_turns: Maximum turns before thief wins.
            group_name: Team/group identifier for result files.
        """
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

        # Populated at run_game() time
        self.game_id: str = ""
        self.game_dir: Path = Path(".")
        self.board: Board = Board(cop_position=[0, 0], thief_position=[6, 6])

        # In-memory stores (also persisted to disk per turn)
        self._my_commits: dict[int, dict] = {}  # step -> full payload incl. nonce

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run_game(self, game_id: str) -> dict:
        """Drive this agent's side of the game to completion.

        Args:
            game_id: Game identifier (received from start_game handshake).

        Returns:
            Result dict: {ok, game_id, role, winner, final_step, audit_ok, …}
        """
        self.game_id = game_id
        self.game_dir = self.games_dir / game_id
        self.game_dir.mkdir(parents=True, exist_ok=True)

        self.board = Board(cop_position=[0, 0], thief_position=[6, 6])
        self._my_commits = {}

        created_at = _now()
        self._save_game_state({"step": 0, "turn": 0, "completed": False,
                               "winner": None, "created_at": created_at})
        logger.info(f"[PeerRuntime/{self.role}] Starting game {game_id}")

        rules = RulesEngine(self.board, max_turns=self.max_turns)
        winner, abort_reason, final_step = await run_peer_turn_loop(self, rules, self.max_turns)

        # Exchange nonces with opponent and run local final audit
        audit_ok, audit_details = await self._do_final_audit(final_step)

        ended_at = _now()
        final_state = {
            "step": self.board.turn, "turn": self.board.turn,
            "cop_position": self.board.cop_position,
            "thief_position": self.board.thief_position,
            "move_history": self.board.move_history,
            "completed": True, "winner": winner,
            "abort_reason": abort_reason, "created_at": created_at,
            "ended_at": ended_at, "final_step": final_step,
            "audit_ok": audit_ok, "audit_details": audit_details,
        }
        self._save_game_state(final_state)
        self._write_result(game_id, final_state, final_step, audit_ok)
        await self._notify_game_end(final_step, winner or "unknown")

        result = {
            "ok": True, "game_id": game_id, "role": self.role,
            "winner": winner, "final_step": final_step,
            "abort_reason": abort_reason, "audit_ok": audit_ok,
        }
        logger.info(f"[PeerRuntime/{self.role}] Game {game_id} done: {result}")
        return result

    # ------------------------------------------------------------------
    # Commit storage (called from peer_turn_loop)
    # ------------------------------------------------------------------

    def _store_my_commit(self, step: int, payload: dict) -> None:
        """Persist my own commitment payload to memory and disk.

        Args:
            step: Turn number.
            payload: Dict with h_commit, nonce, move, hint, intent, state_hash.
        """
        self._my_commits[step] = payload
        path = self.game_dir / f"my_commitments_{self.role}.json"
        existing: dict = {}
        if path.exists():
            with open(path, encoding="utf-8") as f:
                existing = json.load(f)
        existing[str(step)] = payload
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Final audit
    # ------------------------------------------------------------------

    async def _do_final_audit(self, last_step: int) -> tuple[bool, dict]:
        """Send FINAL_AUDIT to opponent, receive their nonces, verify locally."""
        my_nonces = {str(s): p["nonce"] for s, p in self._my_commits.items()}
        msg = ActionMessage(
            game_id=self.game_id, step=last_step, role=self.role,
            config_sha256=self.config_sha256, timestamp=_now(),
            phase="final_audit", nonces=my_nonces,
        )
        try:
            resp = await self.opponent_client.action(self.game_id, msg)
        except Exception as exc:
            logger.error(f"[PeerRuntime] FINAL_AUDIT call failed: {exc}")
            return False, {"error": str(exc)}

        opp_nonces_raw = resp.get("nonces", {})
        opp_nonces = {int(k): v for k, v in opp_nonces_raw.items()}

        audit_ok, details = run_final_audit(
            self.game_dir, self.game_id, self.opponent_role, opp_nonces
        )
        logger.info(f"[PeerRuntime/{self.role}] Final audit: ok={audit_ok} details={details}")
        return audit_ok, details

    # ------------------------------------------------------------------
    # Game end notification
    # ------------------------------------------------------------------

    async def _notify_game_end(self, step: int, winner: str) -> None:
        """Notify opponent that game has ended."""
        msg = ActionMessage(
            game_id=self.game_id, step=step, role=self.role,
            config_sha256=self.config_sha256, timestamp=_now(),
            phase="game_end", reason=winner,
        )
        try:
            await self.opponent_client.action(self.game_id, msg)
        except Exception as exc:
            logger.warning(f"[PeerRuntime] game_end notification failed: {exc}")

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _save_game_state(self, state: dict) -> None:
        path = self.game_dir / "game_state.json"
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def _write_result(
        self, game_id: str, state: dict, final_step: int, audit_ok: bool
    ) -> None:
        """Write the agent-local result file for this game."""
        result = {
            "game_id": game_id, "role": self.role,
            "config_sha256": self.config_sha256,
            "group_name": self.group_name,
            "winner": state.get("winner"),
            "final_step": final_step,
            "abort_reason": state.get("abort_reason"),
            "audit_ok": audit_ok,
            "cop_final_position": self.board.cop_position,
            "thief_final_position": self.board.thief_position,
            "created_at": state.get("created_at"),
            "ended_at": state.get("ended_at"),
            "my_commits_count": len(self._my_commits),
            "opponent_commits_count": len(load_opponent_commits(self.game_dir)),
        }
        path = self.game_dir / f"result_{game_id}.json"
        path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        logger.info(f"[PeerRuntime/{self.role}] Result written: {path}")

    # ------------------------------------------------------------------
    # Strategy hook (can be overridden by orchestrator subclass)
    # ------------------------------------------------------------------

    def _build_observation(self, game_state: dict) -> dict:
        """Build a partial observation dict (hidden-info compliant).

        Subclasses (e.g. GameOrchestrator) override this with the full
        scent/belief observation. Default uses board positions directly.
        """
        if self.role == "cop":
            return {
                "my_position": game_state.get("cop_position", [0, 0]),
                "scent_field": game_state.get("scent_field", []),
                "turn": game_state.get("turn", 0),
            }
        return {
            "my_position": game_state.get("thief_position", [6, 6]),
            "turn": game_state.get("turn", 0),
        }

    def _select_move_rl(self, observation: dict) -> str | None:
        """Hook for RL/strategy move selection. Returns None to use heuristic."""
        return None
