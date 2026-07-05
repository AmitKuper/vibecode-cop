"""Peer-side final audit: each agent verifies the opponent's commitments locally.

No central judge is involved. Each agent independently checks every nonce
revealed by the opponent against the h_commit values it stored at the time
of commitment exchange.
"""

import json
import logging
from pathlib import Path

from agent.mcp.crypto import verify_commitment

logger = logging.getLogger(__name__)


def load_opponent_commits(game_dir: Path) -> dict[int, str]:
    """Load stored opponent h_commits from disk.

    Returns:
        {step: h_commit} or empty dict if file missing.
    """
    path = game_dir / "opponent_commitments.json"
    if not path.exists():
        logger.warning(f"opponent_commitments.json missing in {game_dir}")
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {int(k): v for k, v in raw.items()}


def load_my_reveals(game_dir: Path, role: str) -> dict[int, dict]:
    """Load the locally-stored reveal payloads we received from the opponent.

    These are written by peer_turn_loop at reveal time.

    Returns:
        {step: reveal_dict} or empty dict if file missing.
    """
    path = game_dir / "opponent_reveals.json"
    if not path.exists():
        logger.warning(f"opponent_reveals.json missing in {game_dir}")
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {int(k): v for k, v in raw.items()}


def verify_opponent_reveal(
    h_commit: str,
    reveal: dict,
    game_id: str,
    step: int,
    opponent_role: str,
) -> bool:
    """Verify a single opponent reveal against its stored h_commit.

    Args:
        h_commit: The commitment hash received before revealing.
        reveal: The reveal dict (move, hint, intent, state_hash, nonce).
        game_id: Game identifier.
        step: Turn number.
        opponent_role: "cop" or "thief".

    Returns:
        True if commitment matches, False (tamper detected) otherwise.
    """
    return verify_commitment(
        h_commit=h_commit,
        game_id=game_id,
        step=step,
        role=opponent_role,
        state_hash=reveal.get("state_hash", ""),
        move=reveal.get("move", ""),
        hint=reveal.get("hint", ""),
        intent=reveal.get("intent", ""),
        nonce=reveal.get("nonce", ""),
    )


def run_final_audit(
    game_dir: Path,
    game_id: str,
    opponent_role: str,
    opponent_nonces: dict[int, str],
) -> tuple[bool, dict]:
    """Verify all opponent commitments against revealed nonces locally.

    Called at end-of-game. Each agent runs this independently.

    Args:
        game_dir: Agent-local game directory.
        game_id: Game identifier.
        opponent_role: "cop" or "thief" (the opponent).
        opponent_nonces: {step: nonce} dict received from opponent FINAL_AUDIT.

    Returns:
        (audit_ok, details) where details maps step -> "ok" | error string.
    """
    h_commits = load_opponent_commits(game_dir)
    reveals = load_my_reveals(game_dir, opponent_role)

    verified = 0
    failed = 0
    details: dict[str, str] = {}

    for step, h_commit in h_commits.items():
        nonce = opponent_nonces.get(step)
        reveal = reveals.get(step)

        if nonce is None:
            details[f"step_{step}"] = "missing_nonce"
            failed += 1
            logger.warning(f"[PeerAudit] Missing nonce for step {step}")
            continue

        if reveal is None:
            details[f"step_{step}"] = "missing_reveal"
            failed += 1
            logger.warning(f"[PeerAudit] Missing reveal for step {step}")
            continue

        reveal_with_nonce = {**reveal, "nonce": nonce}
        ok = verify_opponent_reveal(h_commit, reveal_with_nonce, game_id, step, opponent_role)
        if ok:
            verified += 1
            details[f"step_{step}"] = "ok"
        else:
            failed += 1
            details[f"step_{step}"] = "commitment_mismatch"
            logger.warning(
                f"[PeerAudit] Commitment mismatch at step {step} for {opponent_role}"
            )

    audit_ok = failed == 0
    logger.info(
        f"[PeerAudit] {game_id}: {verified} verified, {failed} failed "
        f"(opponent={opponent_role})"
    )
    return audit_ok, details


def append_opponent_commit(game_dir: Path, step: int, h_commit: str) -> None:
    """Persist one opponent h_commit to disk (called after receiving COMMIT).

    Args:
        game_dir: Agent-local game directory.
        step: Turn number.
        h_commit: Commitment hash from opponent.
    """
    path = game_dir / "opponent_commitments.json"
    existing: dict = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            existing = json.load(f)
    existing[str(step)] = h_commit
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def append_opponent_reveal(game_dir: Path, step: int, reveal: dict) -> None:
    """Persist one opponent reveal dict to disk (called after receiving REVEAL).

    Args:
        game_dir: Agent-local game directory.
        step: Turn number.
        reveal: Reveal payload from opponent (without nonce — nonce comes at audit).
    """
    path = game_dir / "opponent_reveals.json"
    existing: dict = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            existing = json.load(f)
    existing[str(step)] = reveal
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
