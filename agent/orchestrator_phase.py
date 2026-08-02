"""MCP phase-handler mixin for GameOrchestrator (commit, reveal routing)."""

import logging
import socket

from agent.mcp.messages import ActionMessage, StartGameMessage

logger = logging.getLogger(__name__)


def _is_reachable(url: str, timeout: float = 2.0) -> bool:
    try:
        from urllib.parse import urlparse

        p = urlparse(url)
        host = p.hostname or "localhost"
        port = p.port or (443 if p.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class PhaseMixin:
    """Mixin providing MCP phase handlers: start_game, action routing, and commit."""

    role: str
    games_dir: object

    def _on_start_game(self, message: StartGameMessage) -> dict:
        game_id = message.game_id
        logger.info(f"Starting game {game_id}")
        try:
            game_dir = self.games_dir / game_id
            game_dir.mkdir(parents=True, exist_ok=True)
            from agent.peer_runtime import _load_start_positions

            cop_start, thief_start = _load_start_positions()
            initial_state = {
                "step": 0,
                "turn": 0,
                "cop_position": cop_start,
                "thief_position": thief_start,
                "move_history": [],
                "completed": False,
                "winner": None,
            }
            self._save_game_state(game_id, initial_state)
            peer_url = getattr(message, "peer_url", None) or getattr(self, "peer_url", None)
            if peer_url and hasattr(self, "discover_protocol"):
                if _is_reachable(peer_url):
                    try:
                        self.discover_protocol(game_id, peer_url)
                    except Exception as exc:
                        logger.warning(f"MCP discovery failed for game {game_id}: {exc}.")
                else:
                    logger.warning(f"Peer {peer_url} is not reachable — skipping discovery.")
            logger.info(f"Game {game_id} initialized successfully")
            return {"ok": True, "game_id": game_id}
        except Exception as e:
            logger.error(f"Error starting game {game_id}: {e}", exc_info=True)
            return {"ok": False, "error": str(e), "game_id": game_id}

    def _on_action(self, game_id: str, message: ActionMessage) -> dict:
        logger.info(f"Handling action for {game_id} phase={message.phase}")
        try:
            game_state = self._load_game_state(game_id)
            if game_state.get("completed") and message.phase not in ["final_audit", "game_end"]:
                logger.warning(f"Game {game_id} already completed, rejecting {message.phase}")
                return {
                    "ok": False,
                    "error": f"Game already completed. Winner: {game_state.get('winner')}",
                    "game_id": game_id,
                }
            dispatch = {
                "commit": self._handle_commit,
                "reveal": self._handle_reveal,
                "final_audit": self._handle_final_audit,
                "game_end": self._handle_game_end,
            }
            handler = dispatch.get(message.phase)
            if handler is None:
                logger.warning(f"Unknown phase: {message.phase}")
                return {"ok": False, "error": f"Unknown phase: {message.phase}"}
            return handler(game_id, message)
        except Exception as e:
            logger.error(f"Error handling action: {e}", exc_info=True)
            return {"ok": False, "error": str(e), "game_id": game_id}

    def _handle_commit(self, game_id: str, message: ActionMessage) -> dict:
        """Handle COMMIT phase: select move, create commitment, return h_commit."""
        try:
            from agent.mcp.crypto import create_commitment, hash_game_state

            board_state = message.board_state
            if board_state:
                game_state = dict(board_state)
                if self.role == "thief":
                    game_state["last_revealed_cop_pos"] = board_state.get("cop_position")
                self._save_game_state(game_id, game_state)
            else:
                game_state = self._load_game_state(game_id)
            observation = self._build_observation(game_state)
            move_str = self._select_move_rl(observation) or self._select_move_llm(
                game_id, observation
            )
            from agent.peer_runtime import _load_start_positions as _starts

            _cop_start, _thief_start = _starts()
            state_hash = hash_game_state(
                {
                    "cop_position": game_state.get("cop_position", _cop_start),
                    "thief_position": game_state.get("thief_position", _thief_start),
                    "turn": game_state.get("turn", 0),
                }
            )
            hint = f"Moving {move_str}"
            intent = "truth"
            h_commit, nonce = create_commitment(
                game_id=game_id,
                step=message.step,
                role=self.role,
                state_hash=state_hash,
                move=move_str,
                hint=hint,
                intent=intent,
            )
            self._store_my_commitment_payload(
                game_id,
                message.step,
                {
                    "h_commit": h_commit,
                    "nonce": nonce,
                    "move": move_str,
                    "hint": hint,
                    "intent": intent,
                    "state_hash": state_hash,
                },
            )
            logger.info(
                f"Committed for {game_id} step {message.step}: "
                f"move={move_str} h_commit={h_commit[:12]}..."
            )
            return {
                "ok": True,
                "game_id": game_id,
                "phase": "commit",
                "step": message.step,
                "h_commit": h_commit,
            }
        except Exception as e:
            logger.error(f"Error in commit phase: {e}", exc_info=True)
            return {"ok": False, "error": str(e)}
