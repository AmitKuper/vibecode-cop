"""GameRunner — drives the full cop-vs-thief turn loop via MCP."""
import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

from agent.board import Board
from agent.game_initiator import GameInitiator
from agent.game_runner_audit import final_audit
from agent.game_runner_output import generate_output_files, write_json
from agent.game_runner_turn import run_turn_loop
from agent.mcp.client import GameMCPClient
from agent.mcp.messages import ActionMessage
from agent.rules_engine import RulesEngine

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class GameRunner:
    """Drives cop and thief agents through the full game loop via MCP."""

    def __init__(
        self,
        cop_url: str = "http://localhost:5000",
        thief_url: str = "http://localhost:5001",
        secret: str = "dev-secret-change-me",
        config_sha256: str = "a" * 64,
        games_dir: Path = Path("agent/memory"),
        max_turns: int = 35,
        group_name: str = "unknown",
        cop_win_score: int = 1,
        thief_win_score: int = 1,
    ):
        self.cop_url = cop_url.rstrip("/")
        self.thief_url = thief_url.rstrip("/")
        self.secret = secret
        self.config_sha256 = config_sha256
        self.games_dir = Path(games_dir)
        self.max_turns = max_turns
        self.group_name = group_name
        self.cop_win_score = cop_win_score
        self.thief_win_score = thief_win_score
        self.cop_client = GameMCPClient(f"{self.cop_url}/mcp", secret)
        self.thief_client = GameMCPClient(f"{self.thief_url}/mcp", secret)
        self._events: list[dict] = []
        self._cop_commits: dict[int, str] = {}; self._thief_commits: dict[int, str] = {}
        self._cop_reveals: dict[int, dict] = {}; self._thief_reveals: dict[int, dict] = {}
        self._game_dir: Path | None = None; self._game_id: str | None = None

    async def run_game(self, game_id: str | None = None) -> dict:
        """Run a complete game. Returns result dict."""
        import uuid
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._game_id = game_id or f"game_{ts}_{uuid.uuid4().hex[:8]}"
        game_id = self._game_id
        self._game_dir = self.games_dir / game_id
        self._game_dir.mkdir(parents=True, exist_ok=True)
        self._events, self._cop_commits, self._thief_commits = [], {}, {}
        self._cop_reveals, self._thief_reveals = {}, {}
        board = Board(cop_position=[0, 0], thief_position=[3, 3])
        rules = RulesEngine(board, max_turns=self.max_turns)
        game_state = {**self._board_to_state(board), "completed": False, "winner": None,
                      "created_at": _now_iso()}
        self._save_game_state(game_state)
        self._log_event("game_start", "initiator", "handshake",
                        {"game_id": game_id, "max_turns": self.max_turns})
        logger.info(f"[GameRunner] Starting game {game_id}")
        if not await self._handshake(game_id):
            self._save_game_state({**game_state, "completed": True, "error": "Handshake failed"})
            self._write_events()
            return {"ok": False, "game_id": game_id, "error": "Handshake failed", "winner": None}
        winner, abort_reason, final_step = await run_turn_loop(self, game_id, board, rules, self.max_turns)
        audit_ok, audit_details = await final_audit(self, game_id, final_step)
        if not audit_ok:
            winner = "TECHNICAL_LOSS"; abort_reason = "commitment_mismatch"
            logger.warning(f"[GameRunner] Audit failed — forcing TECHNICAL_LOSS for {game_id}")
        elif winner is None and abort_reason is None: winner = "thief"
        ended_at = _now_iso()
        final_state = {**self._board_to_state(board), "completed": True, "winner": winner,
                       "abort_reason": abort_reason, "created_at": game_state["created_at"],
                       "ended_at": ended_at, "final_step": final_step,
                       "audit_ok": audit_ok, "audit_details": audit_details}
        self._save_game_state(final_state)
        self._write_events()
        await generate_output_files(self, game_id, final_state, board)
        await self._notify_game_end(game_id, final_step, winner or "unknown", audit_ok)
        result = {"ok": True, "game_id": game_id, "winner": winner,
                  "final_step": final_step, "abort_reason": abort_reason, "audit_ok": audit_ok}
        logger.info(f"[GameRunner] Game {game_id} complete: {result}")
        return result

    async def _handshake(self, game_id: str) -> bool:
        result = await GameInitiator(
            cop_url=f"{self.cop_url}/mcp", thief_url=f"{self.thief_url}/mcp",
            secret=self.secret, config_sha256=self.config_sha256,
        ).start_game(game_id=game_id)
        ok = result.get("ok", False)
        self._log_event("handshake", "initiator", "handshake", {"ok": ok, "game_id": game_id})
        return ok

    def _copy_files_to_agent_dirs(self, game_id: str) -> None:
        src = self._game_dir
        for role in ("cop", "thief"):
            dst = Path(f"{role}/games/{game_id}")
            dst.mkdir(parents=True, exist_ok=True)
            for pattern in (f"declaration_{game_id}.json", f"config_{game_id}_g*.json",
                            f"log_{game_id}_g*.json", f"result_{game_id}.json"):
                for f in src.glob(pattern):
                    shutil.copy2(f, dst / f.name)

    async def _notify_game_end(self, game_id: str, step: int, winner: str, audit_ok: bool) -> None:
        self._copy_files_to_agent_dirs(game_id)
        for client, role in [(self.cop_client, "cop"), (self.thief_client, "thief")]:
            msg = ActionMessage(
                game_id=game_id, step=step, role="initiator",
                config_sha256=self.config_sha256, timestamp=_now_iso(),
                phase="game_end", reason=winner,
            )
            try:
                await client.action(game_id, msg)
            except Exception as e:
                logger.warning(f"[GameRunner] game_end notify to {role} failed: {e}")

    def _board_to_state(self, board: Board) -> dict:
        return {"step": board.turn, "turn": board.turn, "cop_position": board.cop_position,
                "thief_position": board.thief_position, "move_history": board.move_history}

    def _save_game_state(self, state: dict) -> None:
        (self._game_dir / "game_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

    def _log_event(self, event_type: str, role: str, phase: str, details: dict) -> None:
        self._events.append({"timestamp": _now_iso(), "event_type": event_type,
                              "role": role, "phase": phase, "details": details})

    def _write_events(self) -> None:
        events_file = self._game_dir / "events.jsonl"
        try:
            with open(events_file, "w", encoding="utf-8") as f:
                for evt in self._events:
                    f.write(json.dumps(evt, separators=(",", ":")) + "\n")
        except Exception as e:
            logger.error(f"Failed to write events: {e}")

    def _write_json(self, path: Path, data: dict) -> None:
        write_json(path, data)
