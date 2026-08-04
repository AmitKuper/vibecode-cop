"""Game state persistence and reveal mixin for GameOrchestrator."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path  # noqa: F401 — used by subclasses via self.games_dir

from agent.mcp.messages import ActionMessage

logger = logging.getLogger(__name__)


class GameStateMixin:
    """Mixin providing game-state load/save, commitment storage, and reveal."""

    games_dir: Path  # set by GameOrchestrator.__init__
    role: str

    def _load_game_state(self, game_id: str) -> dict:
        """Load game state from memory, returning initial state if not found."""
        state_file = self.games_dir / game_id / "game_state.json"
        if state_file.exists():
            with open(state_file) as f:
                return json.load(f)
        return {
            "step": 0,
            "turn": 0,
            "cop_position": [0, 0],
            "thief_position": [6, 6],
            "move_history": [],
        }

    def _save_game_state(self, game_id: str, state: dict) -> bool:
        """Save game state to memory; returns True on success."""
        try:
            game_dir = self.games_dir / game_id
            game_dir.mkdir(parents=True, exist_ok=True)
            state_file = game_dir / "game_state.json"
            with open(state_file, "w") as f:
                json.dump(state, f, indent=2)
            logger.debug(f"Saved game state for {game_id}")
            return True
        except Exception as e:
            logger.error(f"Error saving game state: {e}", exc_info=True)
            return False

    def _append_move(self, game_id: str, step: int, cop_move: str, thief_move: str) -> None:
        """Append move record to moves.jsonl."""
        try:
            game_dir = self.games_dir / game_id
            game_dir.mkdir(parents=True, exist_ok=True)
            with open(game_dir / "moves.jsonl", "a") as f:
                f.write(
                    json.dumps(
                        {
                            "step": step,
                            "cop_move": cop_move,
                            "thief_move": thief_move,
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )
                    + "\n"
                )
            logger.debug(f"Appended move to {game_id}")
        except Exception as e:
            logger.error(f"Error appending move: {e}", exc_info=True)

    def _save_commitment(self, game_id: str, role: str, step: int, h_commit: str) -> None:
        """Save opponent commitment hash to commitments.json."""
        try:
            game_dir = self.games_dir / game_id
            game_dir.mkdir(parents=True, exist_ok=True)
            commit_file = game_dir / "commitments.json"
            commitments: dict = {}
            if commit_file.exists():
                with open(commit_file) as f:
                    commitments = json.load(f)
            commitments.setdefault(role, {})[str(step)] = h_commit
            with open(commit_file, "w") as f:
                json.dump(commitments, f, indent=2)
            logger.debug(f"Saved commitment for {game_id} {role} step {step}")
        except Exception as e:
            logger.error(f"Error saving commitment: {e}", exc_info=True)

    def _store_my_commitment_payload(self, game_id: str, step: int, payload: dict) -> None:
        """Persist full commit payload (incl. nonce) for later reveal/audit."""
        try:
            game_dir = self.games_dir / game_id
            game_dir.mkdir(parents=True, exist_ok=True)
            my_file = game_dir / f"my_commitments_{self.role}.json"
            data: dict = {}
            if my_file.exists():
                with open(my_file) as f:
                    data = json.load(f)
            data[str(step)] = payload
            with open(my_file, "w") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Stored own commitment payload for {game_id} step {step}")
        except Exception as e:
            logger.error(f"Error storing commitment payload: {e}", exc_info=True)

    def _load_my_commitment_payload(self, game_id: str, step: int) -> dict | None:
        """Load stored commit payload for a given step."""
        try:
            my_file = self.games_dir / game_id / f"my_commitments_{self.role}.json"
            if not my_file.exists():
                return None
            with open(my_file) as f:
                data = json.load(f)
            return data.get(str(step))
        except Exception as e:
            logger.error(f"Error loading commitment payload: {e}", exc_info=True)
            return None

    def _handle_reveal(self, game_id: str, message: ActionMessage) -> dict:
        """Handle REVEAL phase: return the pre-committed move and nonce.

        The GameRunner sends a reveal REQUEST. This agent loads the commitment
        payload stored during COMMIT and returns it unchanged — move is fixed.
        """
        try:
            payload = self._load_my_commitment_payload(game_id, message.step)
            if not payload:
                logger.error(
                    f"No stored commitment for {game_id} step {message.step} "
                    f"— was commit called first?"
                )
                return {
                    "ok": False,
                    "error": f"No stored commitment for step {message.step}",
                    "game_id": game_id,
                }
            logger.info(
                f"Revealing for {game_id} step {message.step}: "
                f"move={payload['move']} h_commit={payload['h_commit'][:12]}..."
            )
            return {
                "ok": True,
                "game_id": game_id,
                "phase": "reveal",
                "step": message.step,
                "move": payload["move"],
                "hint": payload.get("hint"),
                "intent": payload.get("intent"),
                "state_hash": payload["state_hash"],
                "h_commit": payload["h_commit"],
            }
        except Exception as e:
            logger.error(f"Error in reveal phase: {e}", exc_info=True)
            return {"ok": False, "error": str(e)}
