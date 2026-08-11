#!/usr/bin/env python3
"""Reference-v3 match orchestrator with the REAL trained RL policy (never random).

Drives our side of a reference-v3 series against a peer: negotiate per sub-game,
thief-first sealed turns, mutual audit. Moves come from the trained RecurrentA2C-GRU
policy (load_recurrent_policy + select_action) — NOT random. Scent transmitted on the
wire is the byte-exact multiplicative_book_v1 field around our own position.

Validation entry point:
    cd vibecode-cop
    python scripts/live_match_ref3.py --self-test          # vs local sparring peer
    python scripts/live_match_ref3.py --self-test --role thief

Real match (once peer endpoints + course code are known) is a thin wrapper over
_play_subgame with the peer URL and our negotiated role.
"""

from __future__ import annotations

import argparse
import asyncio
import json as _json
import secrets
import socket
import subprocess
import sys
import time
from datetime import UTC
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
KIT_ROOT = REPO_ROOT.parent / "external" / "copthief-league-protocol"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
# Ensure the sibling ref3_artifacts module is importable regardless of how we're launched.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

# Cop barrier placement: target cell = own_position + delta (mirrors domain/transition.py).
_PLACE_DELTAS = {"PLACE_N": (0, -1), "PLACE_S": (0, 1), "PLACE_E": (1, 0), "PLACE_W": (-1, 0)}

# Runtime params (timeouts, reorder window, ...) sourced from config/runtime.toml at match
# start via apply_runtime_config(). Empty by default so the self-test / unit tests keep the
# original hardcoded fallbacks passed to _t().
_RT: dict = {}


def _t(key: str, default):
    """Read a [timeouts] value from the applied runtime config, else the hardcoded fallback."""
    return _RT.get("timeouts", {}).get(key, default)


def apply_runtime_config(runtime: dict) -> None:
    """Install a loaded runtime.toml (from config_loader) for the helpers below to read."""
    global _RT
    _RT = dict(runtime or {})


# ---------------------------------------------------------------------------
# RL move engine — the whole point: real policy, not random.
# ---------------------------------------------------------------------------
class RLMover:
    """Wraps the trained role policy and tracks own position + emitted scent."""

    def __init__(
        self,
        role: str,
        terms: dict,
        scent_model: str = "multiplicative_book_v1",
        move_policy: str = "rl",
    ) -> None:
        from cop_worker.board import Board
        from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS

        # Architecture-dispatching loader: the cop is RecurrentA2C-GRU and the thief may be a
        # DuelingDoubleDQN — load_counted_policy handles both (delegates recurrent internally).
        from cop_worker.rl.counted_policy import load_counted_policy

        self.role = role  # "police" (cop) or "thief"
        self.terms = terms
        self.scent_model = scent_model
        self.grid = terms["board_size"]
        self.actions = COP_ACTIONS if role == "police" else THIEF_ACTIONS
        # Role-split: our cop model lives in this repo; our thief model in the
        # sibling thief repo. Each worker owns its own trained policy.
        if role == "police":
            manifest = REPO_ROOT / "models" / "MANIFEST.json"
            manifest_role = "cop"
        else:
            manifest = REPO_ROOT.parent / "vibecode-thief" / "models" / "MANIFEST.json"
            manifest_role = "thief"
        self.policy = load_counted_policy(manifest, manifest_role)
        # Hybrid serving: minimax over exact chebyshev tracking with the RL policy as
        # fallback for blind frames. Only meaningful when the locked model makes the
        # frame an oracle; the plain RL path stays byte-identical under "rl".
        if move_policy in ("hybrid_search", "hybrid_search_belief"):
            from cop_worker.rl.search_policy import wrap_with_search

            self.policy = wrap_with_search(
                self.policy,
                manifest_role,
                terms,
                belief_mode=(move_policy == "hybrid_search_belief"),
            )
        elif move_policy != "rl":
            raise ValueError(f"unknown move_policy {move_policy!r}")
        start = terms["cop_start"] if role == "police" else terms["thief_start"]
        self.pos = [int(start[0]), int(start[1])]  # [x, y]
        # Cop barrier state (thief never places): quota, placed cells, last placement.
        self.barriers_remaining = int(terms.get("barriers_max", 0)) if role == "police" else 0
        self.barriers: list[list[int]] = []
        self.last_barrier: list[int] | None = None
        # A board whose "thief" cell we drive to OUR position, so update_scent emits
        # the byte-exact book field around us regardless of role.
        self._board = Board(cop_position=[0, 0], thief_position=list(self.pos), grid_size=self.grid)
        from cop_worker.rules_engine import RulesEngine

        self._rules = RulesEngine(self._board, max_turns=terms["max_steps"])
        # Locked-model dispatch for our own emission: under subtractive_chebyshev_v1 the
        # trail lives in ChebyshevTrail (kit-exact rings/merge-by-max/subtractive decay,
        # 0.8-peak wire snapshots); the book engine above stays for multiplicative_book_v1.
        self._chebyshev_trail = None
        if scent_model == "subtractive_chebyshev_v1":
            from cop_worker.scent_chebyshev import ChebyshevTrail

            self._chebyshev_trail = ChebyshevTrail(
                self.grid,
                field_size=int(terms.get("smell_grid_size", 5)),
                emit_intensity=float(terms.get("emit_intensity", 0.9)),
                decay_per_step=float(terms.get("decay_per_step", 0.1)),
                min_center_intensity=float(terms.get("min_center_intensity", 0.5)),
            )

    def _opponent_scent_grid(self, smell_grid: dict) -> list[list[float]]:
        """Convert the peer's transmitted {'r,c': v} field to our NxN grid."""
        n = self.grid
        g = [[0.0] * n for _ in range(n)]
        for cell, val in (smell_grid or {}).items():
            try:
                r, c = (int(t) for t in cell.split(","))
            except (ValueError, AttributeError):
                continue
            if 0 <= r < n and 0 <= c < n:
                g[r][c] = float(val)
        return g

    def decide(self, step: int, sub_game: int, opponent_smell: dict, opponent_hint: str) -> str:
        """Return the RL-chosen action for this step (never random)."""
        from cop_worker.observation import BeliefState, LocalObservation

        obs = LocalObservation(
            own_position=(self.pos[0], self.pos[1]),
            own_barriers_remaining=self.barriers_remaining,
            known_barriers=[tuple(b) for b in self.barriers],
            opponent_scent=self._opponent_scent_grid(opponent_smell),
            last_hint=opponent_hint or "",
            step=step,
            gamelet=sub_game,
            grid_size=self.grid,
        )
        belief = BeliefState.uniform(self.grid, step=step)
        # Pass the TRUE legal action set (board edges + barriers + quota), matching training.
        # The full list let the policy propose off-board moves the domain clamps to STAY, which
        # froze the cop at its start cell (never pursuing). Mask per role.
        from cop_worker.rl.action_space import (
            compute_legal_mask_cop,
            compute_legal_mask_thief,
        )

        if self.role == "police":
            mask = compute_legal_mask_cop(
                tuple(self.pos),
                [tuple(b) for b in self.barriers],
                self.barriers_remaining,
                self.grid,
            )
        else:
            mask = compute_legal_mask_thief(
                tuple(self.pos),
                [tuple(b) for b in self.barriers],
                self.grid,
            )
        legal = [a for a, m in zip(self.actions, mask) if m] or list(self.actions)
        action = self.policy.select_action(obs, belief, legal)
        return action

    def apply(self, action: str) -> None:
        """Apply the chosen action: move (N/S/E/W), STAY, or place a barrier.

        A PLACE_* forfeits movement (position unchanged) and, if legal (quota left,
        target in-bounds and not already blocked), records the barrier cell so it goes
        on the wire as barrier_placed and is fed back into the next observation.
        """
        self.last_barrier = None
        if action in _PLACE_DELTAS:
            if self.role == "police" and self.barriers_remaining > 0:
                dx, dy = _PLACE_DELTAS[action]
                bx, by = self.pos[0] + dx, self.pos[1] + dy
                if 0 <= bx < self.grid and 0 <= by < self.grid and [bx, by] not in self.barriers:
                    self.barriers.append([bx, by])
                    self.barriers_remaining -= 1
                    self.last_barrier = [bx, by]
            return  # placement (legal or not) forfeits the move
        x, y = self.pos
        if action == "N" and y > 0:
            y -= 1
        elif action == "S" and y < self.grid - 1:
            y += 1
        elif action == "E" and x < self.grid - 1:
            x += 1
        elif action == "W" and x > 0:
            x -= 1
        self.pos = [x, y]

    def observe_peer_barrier(self, cell) -> None:
        """Track a cop-placed barrier while WE are the thief.

        Training always fed the thief the true barrier list (``known_barriers`` +
        the legal-move mask in ``train_recurrent._observation``); serving fed ``[]``,
        so the net could neither route around walls nor know it was enclosed. As cop,
        ``self.barriers`` are OUR placements and the peer thief never places — ignore.
        """
        if self.role != "thief" or not isinstance(cell, (list, tuple)) or len(cell) != 2:
            return
        try:
            bx, by = int(cell[0]), int(cell[1])
        except (TypeError, ValueError):
            return
        if 0 <= bx < self.grid and 0 <= by < self.grid and [bx, by] not in self.barriers:
            self.barriers.append([bx, by])

    def self_capture_check(self) -> str | None:
        """Rule 46/47 self-check — the endings only the thief can see (must be SAID).

        Rule 46: a barrier on our cell is a capture. Rule 47: no orthogonal escape
        (every neighbour barrier or off-board) is a capture — STAY does not rescue.
        Returns "rule46"/"rule47" or None. Silence here forks the game: we'd claim a
        survival the cop's audit scores as capture — the rule-35 shape that zeroes
        BOTH teams (imreeyal §3.14, kit WARNINGS §5c).
        """
        if self.role != "thief":
            return None
        x, y = self.pos
        if [x, y] in self.barriers:
            return "rule46"
        for dx, dy in ((0, -1), (0, 1), (1, 0), (-1, 0)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.grid and 0 <= ny < self.grid and [nx, ny] not in self.barriers:
                return None
        return "rule47"

    def our_smell_grid(self) -> dict:
        """Byte-exact scent around our own position under the LOCKED model, wire {'r,c': v}."""
        if self._chebyshev_trail is not None:
            # Wire key is "row,col"; our pos is [x, y] → center (y, x).
            return self._chebyshev_trail.full_turn((self.pos[1], self.pos[0]))
        self._board.thief_position = list(self.pos)  # emitter = us
        self._rules.update_scent()
        field = self._rules.get_scent_field()
        n = self.grid
        return {f"{r},{c}": field[r][c] for r in range(n) for c in range(n) if field[r][c] > 0.0}


def _to_wire_cell(cell) -> list[int] | None:
    """Our internal [x, y] -> the kit's wire [row, col].

    The kit's convention is authoritative: its turnloop feeds ``engine.position``
    straight into ``ref_smell_emit``, whose keys are ``"row,col"`` — so every
    cell-valued wire field (position, barrier_placed, capture_claim,
    claim_response.claim) is [row, col]. We found this live (2026-08-10 rehearsal):
    our [x, y] barrier registered TRANSPOSED in the peer's physics, its thief
    legally dodged "through" our wall, and off-diagonal captures could never
    settle. Internal state stays [x, y]; conversion happens only at the boundary.
    """
    if not isinstance(cell, (list, tuple)) or len(cell) != 2:
        return None
    return [int(cell[1]), int(cell[0])]


def _from_wire_cell(cell) -> list[int] | None:
    """The kit's wire [row, col] -> our internal [x, y]."""
    return _to_wire_cell(cell)  # transposition is its own inverse


def _corroborate_caught(cell, our_claim, our_barriers, our_pos, grid) -> tuple[str, bool]:
    """Classify and live-corroborate a thief ``caught=true`` (SPEC §3.1).

    ANSWER: the cell echoes our last capture_claim → co-location, corroborated by
    construction (we claimed our own cell). CONCESSION: any other cell — corroborated
    only under OUR OWN barrier record (a barrier of ours on that cell, rule 46, or every
    orthogonal neighbour ours/off-board, rule 47), never under the thief's reported
    list. The trail-end refinement happens at audit time, once records are revealed.
    """
    if not isinstance(cell, (list, tuple)) or len(cell) != 2:
        return "malformed", False
    cell = [int(cell[0]), int(cell[1])]
    if our_claim is not None and cell == list(our_claim):
        return "answer", True
    ours = [list(b) for b in our_barriers]
    if cell in ours:
        return "concession", True
    for dx, dy in ((0, -1), (0, 1), (1, 0), (-1, 0)):
        nx, ny = cell[0] + dx, cell[1] + dy
        if 0 <= nx < grid and 0 <= ny < grid and [nx, ny] not in ours:
            return "concession", False
    return "concession", True


class _TimestampedTee:
    """Mirror a stream to a log file, stamping wall-clock time at each line start.

    Installed over stdout+stderr for a real match so every line — ours, uvicorn's,
    tracebacks — lands in one timestamped file. Deadline disputes (the signed 30s
    response budget, their 180s turn budget) are evidence questions; an unstamped
    console scrollback answers none of them.
    """

    def __init__(self, stream, sink) -> None:
        self._stream = stream
        self._sink = sink
        self._at_line_start = True

    def write(self, text: str) -> int:
        n = self._stream.write(text)
        from datetime import datetime

        for piece in text.splitlines(keepends=True):
            if self._at_line_start and piece.strip():
                self._sink.write(datetime.now().strftime("%H:%M:%S.%f")[:-3] + " ")
            self._sink.write(piece)
            self._at_line_start = piece.endswith("\n")
        self._sink.flush()
        return n

    def flush(self) -> None:
        self._stream.flush()
        self._sink.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def _wire_session_class():
    """A ReferenceV3Session that logs INBOUND wire metadata — names/fields, never bodies.

    WARNINGS §2c: a team that logs only its own view cannot log an ABSENCE, and the one
    fact that matters in a stall ("what did you actually receive from us?") becomes
    structurally invisible. Metadata only: keys, step numbers, senders, commit prefixes,
    lock hashes. No smell grids, no hint text, and never a nonce of ours.
    """
    from cop_worker.protocol.reference_v3 import ReferenceV3Session

    class WireLoggingSession(ReferenceV3Session):
        def receive_negotiation(self, message: dict) -> None:
            m = message if isinstance(message, dict) else {}
            print(
                f"[wire<-] negotiate keys={sorted(m)} group={m.get('group_id')!r} "
                f"role={m.get('role')!r} sub_game={m.get('sub_game_number')!r} "
                f"uid={str(m.get('game_uid'))[:13]!r} "
                f"scent={str(m.get('scent_model_sha256'))[:8]} "
                f"wire={str(m.get('wire_shape_sha256'))[:8]}"
            )
            super().receive_negotiation(message)

        def receive_turn(self, message: dict) -> list[dict]:
            m = message if isinstance(message, dict) else {}
            print(
                f"[wire<-] turn step={m.get('step')} sender={m.get('sender')!r} "
                f"commit={str(m.get('commit'))[:8]} ts={str(m.get('timestamp'))[:23]!r} "
                f"cells={len(m.get('smell_grid') or {})} "
                f"barrier={m.get('barrier_placed')} claim={m.get('capture_claim')} "
                f"answer={(m.get('claim_response') or {}).get('caught')} "
                f"win={(m.get('win_claim') or {}).get('type')}"
            )
            return super().receive_turn(message)

        def receive_audit(self, payload: dict) -> None:
            p = payload if isinstance(payload, dict) else {}
            print(
                f"[wire<-] audit sender={p.get('sender')!r} "
                f"records={len(p.get('records') or [])} claim={p.get('result_claim')!r}"
            )
            super().receive_audit(payload)

        def receive_control(self, message: dict) -> None:
            m = message if isinstance(message, dict) else {}
            print(
                f"[wire<-] control kind={m.get('kind')!r} sender={m.get('sender')!r} "
                f"sub_game={m.get('sub_game_number')!r} status={m.get('status')!r}"
            )
            super().receive_control(message)

    return WireLoggingSession


def _install_match_log(opponent: str) -> Path:
    """Tee stdout+stderr into a timestamped per-match log file."""
    out_dir = REPO_ROOT / "reports" / "ref3_matches"
    out_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

    path = out_dir / f"match_{opponent}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    sink = open(path, "a", encoding="utf-8")
    sys.stdout = _TimestampedTee(sys.stdout, sink)
    sys.stderr = _TimestampedTee(sys.stderr, sink)
    print(f"[match] logging to {path}")
    return path


_PEER_SCENT_SEEN: dict[int, str] = {}


def _log_peer_scent_model(
    sub_game: int, step: int, smell_grid: dict, ours: str = "multiplicative_book_v1"
) -> None:
    """Print the peer's scent model the first time a frame is decisive, per sub-game.

    Diagnostic only. Early frames are the informative ones: both registered models decay, so
    a late accumulated frame holds intermediate values that belong to neither and classifies
    as ``inconclusive`` rather than guessing.
    """
    if _PEER_SCENT_SEEN.get(sub_game) is not None:
        return
    from cop_worker.protocol.scent_fingerprint import fingerprint

    result = fingerprint(smell_grid)
    model = result["model"]
    if model in ("inconclusive", "empty"):
        return
    _PEER_SCENT_SEEN[sub_game] = model
    if model == ours:
        print(f"[scent] sg{sub_game} step{step}: peer transmits {model} — MATCHES ours")
    else:
        print(
            f"[scent] sg{sub_game} step{step}: *** PEER SCENT MODEL MISMATCH *** "
            f"peer={model} ours={ours} "
            f"(peer cells={result['cells']} max={result['max']} "
            f"distinct={result['distinct']}) — our policy is reading a field at the wrong "
            f"scale; raise this with the opponent before a counted series"
        )


# ---------------------------------------------------------------------------
# Networking helpers
# ---------------------------------------------------------------------------
def _check_port(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex((host, port)) == 0


async def _wait_port(host: str, port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _check_port(host, port):
            return
        await asyncio.sleep(0.15)
    raise TimeoutError(f"no listener on {host}:{port}")


class NoGameHappened(TimeoutError):
    """A window failure BEFORE any opponent step arrived.

    Index-hold rule (agreed with uoh-sqak, 2026-08-12): a sub-game in which no
    game actually happened — discovery failed, no matching greeting, or the peer
    handshook and then never played a step — must NOT spend its index. The
    series loop retries the same number, bounded by time, so a holding peer can
    converge onto it. A window that died AFTER steps were exchanged is spent as
    before (replaying a partially played index would corrupt the audit story).
    """


async def _poll_deque(dq, *, timeout: float, label: str) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if dq:
            return dq.popleft()
        await asyncio.sleep(0.05)
    raise TimeoutError(f"timeout waiting for {label}")


async def _poll_agreement(dq, sub_game: int, *, timeout: float) -> dict:
    """Return the peer greeting whose sub_game_number matches, discarding stale ones.

    The peer re-dials our negotiate across per-window re-runs, so greetings pile up in
    the deque. Consuming FIFO makes us pick a stale greeting (its sub_game lags ours) →
    SPAR-N06. Instead we match by sub_game_number: drop older greetings, keep newer.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        keep, found = [], None
        while dq:
            msg = dq.popleft()
            n = msg.get("sub_game_number")
            if found is None and (n == sub_game or not isinstance(n, int)):
                found = msg
            elif isinstance(n, int) and n < sub_game:
                continue  # drop stale greeting from an earlier sub-game
            else:
                keep.append(msg)  # a greeting for a later sub-game — keep it
        dq.extend(keep)
        if found is not None:
            return found
        await asyncio.sleep(0.05)
    raise NoGameHappened(f"timeout waiting for negotiate matching sub_game {sub_game}")


async def _poll_turn(inbox, step: int, *, timeout: float, session=None) -> dict:
    """Wait until the inbox has the opponent's turn for `step`; return it.

    On timeout the error carries the diagnosis a stalled peer needs: which step we
    were owed, which steps actually played, and the peer's last inbound turn — the
    "your step k never arrived; your last was k-1 at HH:MM:SS" line that separates
    OUR stall from THEIRS in one read.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if step in inbox.played or inbox.next_step > step:
            return inbox.turn_for(step) if hasattr(inbox, "turn_for") else {}
        await asyncio.sleep(0.05)
    played = sorted(inbox.played)
    last = None
    if session is not None and getattr(session, "turn_messages", None):
        m = session.turn_messages[-1]
        last = (m.get("step"), m.get("sender"), str(m.get("timestamp"))[:23])
    # Zero opponent steps ever = a zero-turn window (never settles, files no row):
    # retriable at the same index. Any played step means the game truly started.
    err_cls = NoGameHappened if not played else TimeoutError
    raise err_cls(
        f"timeout after {timeout:.0f}s waiting for opponent turn step {step}; "
        f"steps played={played or 'none'}, buffered={sorted(inbox.buffered) or 'none'}, "
        f"their last inbound turn={last or 'NONE EVER'}"
    )


async def _await_endpoint(mcp_url: str, client_cls, *, window_s: float = 900.0) -> bool:
    """Poll ONE peer MCP URL until it answers list_tools (its window opens), or timeout.

    The peer binds its cop/thief endpoint only during that role's sub-game window, so we
    wait for the specific endpoint we must dial and tolerate transient 502/530/refused
    (its origin is down between windows) rather than treating them as fatal.
    """
    deadline = time.monotonic() + window_s
    announced = False
    while time.monotonic() < deadline:
        try:
            async with client_cls(mcp_url) as c:
                await c.list_tools()
            print(f"[match] peer endpoint UP: {mcp_url}")
            return True
        except Exception as exc:
            if not announced:
                print(
                    f"[match] waiting for peer endpoint {mcp_url} "
                    f"({type(exc).__name__}: {str(exc)[:80]})"
                )
                announced = True
            await asyncio.sleep(8)
    return False


# ---------------------------------------------------------------------------
# One sub-game over the reference-v3 wire, driven by the RL policy.
# ---------------------------------------------------------------------------
async def _play_subgame(
    out_session,
    in_session,
    *,
    role: str,
    sub_game: int,
    group_id: str,
    group_name: str,
    terms: dict,
    opponent_group_hint: str,
    members: list | None = None,
    our_counted: int = 0,
    scent_model: str = "multiplicative_book_v1",
    move_policy: str = "rl",
    declared_opponent_group: str | None = None,
) -> dict:
    from ref3_artifacts import OUR_MCP, OUR_REPOS

    from cop_worker.protocol.reference_v3 import (
        ReferenceV3Inbox,
        build_negotiation,
        build_turn,
        reference_commit,
        verify_audit,
        verify_negotiation,
    )

    # Our step-zero identity on the wire (rules 49/53): repos, per-role github_commit,
    # counted count, members — so the peer records what we actually declare.
    our_repo = REPO_ROOT if role == "police" else REPO_ROOT.parent / "vibecode-thief"
    our_commit = _git_head(our_repo)
    our_identity = {
        "group_id": group_id,
        "group_name": group_name,
        # Honest declaration: movement is the trained role-specific RL policy; the verbal layer
        # is template-generated (no language model is called during play, so no LLM tokens are
        # consumed). The book forbids letting a model decide movement, and hints provably cannot
        # affect ours — local_obs_to_tensor never reads last_hint.
        "llm_model": "none (template hints; role-specific-recurrent-policy movement)",
        "mcp_servers": OUR_MCP,
        "repos": OUR_REPOS,
        "members": members or [],
        "github_commit": our_commit,
        "counted_games_played": our_counted,
    }

    max_steps = terms["max_steps"]
    # Fresh per-sub-game state: sealed records and the inbox must never leak across
    # sub-games (else step 1 of the next sub-game equivocates against the last one).
    out_session.local_records = []
    out_session._local_records_by_step = {}
    in_session.turns = ReferenceV3Inbox(window=_t("reorder_window", 4))
    in_session.turn_messages.clear()
    in_session.expected_turn_sender = None
    in_session.audits.clear()  # drain stale end-of-game payloads from prior sub-games
    in_session.controls.clear()
    from datetime import datetime

    started_at = datetime.now(UTC).isoformat()
    nonce = secrets.token_hex(16)
    # Declare our derived game_uid ONLY when the opponent's group_id is actually known — a
    # configured pairing, or learned from sub-game 1's verified greeting. Kit §7.3: both
    # declare and differ → refuse, so declaring from a guessed group would refuse every
    # handshake; omission never refuses. Formula parity with the kit is pinned by tests.
    greeting = build_negotiation(
        terms=terms,
        nonce=nonce,
        group_id=group_id,
        group_name=group_name,
        role=role,
        sub_game_number=sub_game,
        identity=our_identity,
        opponent_group=declared_opponent_group,
        scent_model=scent_model,
    )
    await out_session.send_negotiation(greeting)
    # Match the greeting by sub_game_number (not FIFO) — the peer's re-dials pile up.
    theirs = await _poll_agreement(
        in_session.agreements, sub_game, timeout=_t("agreement_poll_sec", 300.0)
    )
    opp_identity = theirs.get("identity") or {}  # their declared repos/commit/counted (rules 49/53)
    print(
        f"[match] sg{sub_game} peer greeting sub_game={theirs.get('sub_game_number')} "
        f"role={theirs.get('role')}"
    )
    try:
        negotiated = verify_negotiation(greeting, theirs)
    except Exception as exc:
        # A refusal is only actionable if it names the DIFF, not just the rule. This
        # block is what turns "handshake failed" into an instruction for the peer.
        t_terms = theirs.get("terms") if isinstance(theirs.get("terms"), dict) else {}
        ours_terms = greeting["terms"]
        key_diff = sorted(set(ours_terms) ^ set(t_terms))
        val_diff = {
            k: (ours_terms.get(k), t_terms.get(k))
            for k in ours_terms
            if k in t_terms and ours_terms[k] != t_terms[k]
        }
        print(f"[match] sg{sub_game} HANDSHAKE REFUSED: {exc}")
        print(f"[diag ] terms key diff (ours^theirs): {key_diff or 'none'}")
        print(f"[diag ] terms value diff (ours vs theirs): {val_diff or 'none'}")
        print(
            f"[diag ] locks ours scent={greeting.get('scent_model_sha256', '')[:12]} "
            f"wire={greeting.get('wire_shape_sha256', '')[:12]} | theirs "
            f"scent={str(theirs.get('scent_model_sha256'))[:12]} "
            f"wire={str(theirs.get('wire_shape_sha256'))[:12]}"
        )
        print(
            f"[diag ] uid ours={greeting.get('game_uid')} theirs={theirs.get('game_uid')} "
            f"role ours={greeting.get('role')} theirs={theirs.get('role')} "
            f"sub_game ours={sub_game} theirs={theirs.get('sub_game_number')}"
        )
        raise
    print(
        f"[match] sg{sub_game} role={role} handshake OK vs {negotiated.opponent_group} "
        f"uid={negotiated.game_uid[:12]}"
    )

    # Step-0 sealed ON the wire: a fresh-nonce commitment of our identity (github_commit,
    # declaration_ref) that rides submit_audit as records[0] — matching anrbj666's g01 recipe
    # byte-for-byte. The peer's verify_audit rehashes it; step 0 is exempt from the played
    # binding (step >= 1 only), so it is a sealed record, not just the negotiate identity.
    sz_payload = {
        "declaration_ref": f"declaration_{negotiated.game_id}.json",
        "github_commit": our_commit,
        "group_id": group_id,
        "role": role,
        "step": 0,
        "sub_game_number": sub_game,
        "type": "step_zero",
    }
    sz_nonce = secrets.token_hex(16)
    step_zero_record = {
        "payload": sz_payload,
        "nonce": sz_nonce,
        "commit": reference_commit(sz_payload, sz_nonce),
    }
    out_session.local_records.append(step_zero_record)  # records[0], sent in submit_audit
    out_session._local_records_by_step[0] = step_zero_record

    mover = RLMover(role, terms, scent_model=scent_model, move_policy=move_policy)
    # One sub-game == one episode. Without this the GRU hidden state (and the scent decoder's
    # previous-frame memory) carried over from the PREVIOUS sub-game, so sub-games 2..6 started
    # mid-thought on a board that had just been reset -- every match we have played so far,
    # counted ones included. Training always resets between episodes; serving never did.
    mover.policy.reset()
    # Free-language hint policy. Template-only (llm_hint_generator=None): the LLM is provably
    # irrelevant to play — local_obs_to_tensor never reads last_hint, so no hint (ours or the
    # opponent's) can shift a single move — and templates cost zero latency and add no
    # external-service dependency mid-match. What this DOES buy is deception: the driver used
    # to send hint=f"moving {action}" with intent hardcoded "truth", i.e. it broadcast our exact
    # move truthfully every step for any hint-reading opponent to exploit.
    from cop_worker.language.deception_policy import NaturalLanguagePolicy

    nlp = NaturalLanguagePolicy(role="cop" if role == "police" else "thief")
    we_move_first = role == "thief"  # reference-v3: THIEF moves first every sub-game
    rl_moves: list[str] = []
    pending_answer: dict | None = None  # thief's answer to a cop capture_claim (rides next turn)
    captured = False  # True if this sub-game ended in a capture (either direction)
    our_last_claim: list[int] | None = None  # cop: the cell our last capture_claim named
    disputed_capture: dict | None = None  # a caught=true we could NOT corroborate (audit note)
    settled_caught_cell: list[int] | None = None  # the cell a caught=true settled on

    for step in range(1, max_steps + 1):
        if not we_move_first:
            # cop: wait for the thief's sealed turn first, absorb its scent/hint.
            await _poll_turn(
                in_session.turns, step, timeout=_t("turn_poll_sec", 120.0), session=in_session
            )
            opp = _latest_turn(in_session, step)
            # A caught=true from the thief settles CAPTURE — but corroborate which KIND
            # (SPEC §3.1): a cell echoing our last claim is an ANSWER (co-location); any
            # other cell is a CONCESSION (rule 46/47) and must be captured under OUR OWN
            # barrier record — never under the barrier list the thief reports. A failed
            # corroboration still ends the game but is recorded as disputed, not clean.
            _cr = opp.get("claim_response") or {}
            if _cr.get("caught") is True:
                _cell = _cr.get("claim")  # wire [row, col]
                if isinstance(_cell, (list, tuple)) and len(_cell) == 2:
                    settled_caught_cell = [int(_cell[0]), int(_cell[1])]  # keep wire form
                _kind, _clean = _corroborate_caught(
                    _from_wire_cell(_cell) or _cell,
                    our_last_claim,
                    mover.barriers,
                    mover.pos,
                    mover.grid,
                )
                if not _clean:
                    disputed_capture = {
                        "cell": _cell,
                        "kind": _kind,
                        "our_claim": our_last_claim,
                        "our_barriers": [list(b) for b in mover.barriers],
                    }
                    print(
                        f"[match] sg{sub_game} step {step}: caught=true did NOT "
                        f"corroborate ({_kind}, cell={_cell}) — recording disputed"
                    )
                else:
                    print(f"[match] sg{sub_game} thief conceded capture at step {step} ({_kind})")
                captured = True
                break
            # Thief declared the survival terminal on its final step: the game is settled
            # before the cop moves (the reference cop ends at 34). Stop sealing here — a
            # post-terminal cop move could otherwise write a capture-shaped record into an
            # already-settled survival (anrbj666's flagged wart). Our count = thief count - 1.
            if (opp.get("win_claim") or {}).get("type") == "survival":
                print(
                    f"[match] sg{sub_game} thief declared survival terminal at step {step}; cop stops (no post-terminal move)"
                )
                break
        else:
            # Thief moves FIRST: at round r the cop's newest turn is numbered r-1
            # (per-sender numbering), so an exact step-r lookup matched NOTHING and
            # the thief played every round blind — tracker dry, RL fallback only
            # (found live 2026-08-10: identical thief rollouts across different
            # search evals gave it away). Absorb the cop's r-1 turn instead.
            opp = _latest_turn(in_session, step - 1) if step > 1 else {}

        opp_hint = opp.get("hint", "")
        opp_smell = opp.get("smell_grid", {})
        # Log-only: which registered scent_model is the peer actually transmitting? The kit's
        # refusal rule is "only when BOTH peers declare a family and disagree", so an
        # undeclared mismatch passes the mutual audit silently -- and our policy would be
        # reading a field at the wrong scale with no warning. Read it off the wire instead.
        # Purely diagnostic: never gates a move, so match behaviour is unchanged.
        _log_peer_scent_model(sub_game, step, opp_smell, ours=scent_model)
        action = mover.decide(step, sub_game, opp_smell, opp_hint)
        rl_moves.append(action)
        mover.apply(action)
        # Profile the opponent's language. No trustworthy= verdict is passed: during play their
        # move stays sealed until the final audit, so we have no ground truth to judge the hint
        # against and must not fabricate one (the trust model then holds at its 0.5 default).
        if opp_hint:
            nlp.record_opponent_hint(opp_hint)
        # Language is chosen independently of movement (the book's requirement) and may lie.
        intent = nlp.choose_intent(
            step=step,
            gamelet=sub_game,
            physical_action=action,
            token_budget=int(terms.get("hint_max_words", 15)),
        )
        hint_text = nlp.generate(action, intent)
        # Hard clamp to the negotiated word cap: validate_turn rejects a longer hint outright,
        # and a counted series is one-shot — never risk it on template wording.
        _cap = int(terms.get("hint_max_words", 15))
        if len(hint_text.split()) > _cap:
            hint_text = " ".join(hint_text.split()[:_cap])
        record_payload = {
            "step": step,
            "role": role,
            "sub_game": sub_game,
            "position": _to_wire_cell(mover.pos),
            "move": action,
            "intent": intent.value,
        }
        if mover.last_barrier is not None:
            record_payload["barrier_placed"] = _to_wire_cell(mover.last_barrier)
        # A pending capture-claim answer (thief only) rides this turn; caught => terminal.
        answer, pending_answer = pending_answer, None
        caught = bool(answer and answer.get("caught"))
        step_nonce = secrets.token_hex(16)
        # Survival terminal on the thief's final step (unless it's a caught answer);
        # the blind cop needs it or it waits out its budget (kit turnloop.py:183,303).
        win_claim = (
            {"type": "survival"} if (role == "thief" and step == max_steps and not caught) else None
        )
        # The cop claims its own cell EVERY turn — the reference peer's own policy
        # (kit turnloop.py:169): the claim just asks "am I standing on you?", the
        # thief's honest answer settles co-location, and there is no claim penalty.
        # Without this our cop could never initiate a capture settlement at all.
        capture_claim = _to_wire_cell(mover.pos) if role == "police" else None
        if capture_claim is not None:
            our_last_claim = list(mover.pos)  # internal [x, y] for corroboration
        turn, record = build_turn(
            record_payload=record_payload,
            nonce=step_nonce,
            sender=role,
            hint=hint_text,
            smell_grid=mover.our_smell_grid(),
            barrier_placed=_to_wire_cell(mover.last_barrier),
            capture_claim=capture_claim,
            claim_response=answer,
            win_claim=win_claim,
        )
        await out_session.send_turn(turn, record)
        if caught:
            print(f"[match] sg{sub_game} our thief answered caught=true at step {step}")
            captured = True
            break
        if we_move_first and win_claim is None:
            # Thief waits for the cop's turn, then prepares an answer to any capture claim
            # it carries (rides our next turn — kit turnloop.py:271-273).
            await _poll_turn(
                in_session.turns, step, timeout=_t("turn_poll_sec", 120.0), session=in_session
            )
            cop_turn = _latest_turn(in_session, step)
            claim = cop_turn.get("capture_claim")  # wire [row, col]
            if claim is not None:
                # Echo the asked cell verbatim (kit convention); compare in wire form.
                pending_answer = {
                    "claim": list(claim),
                    "caught": list(claim) == _to_wire_cell(mover.pos),
                }
            # Track the cop's barrier and run the rule-46/47 self-check on the board it
            # just changed. An ending only we can see must be SAID: the concession is a
            # real STAY turn whose field advances (an empty grid reads as vanished scent
            # to a strict physics checker), and it supersedes any pending answer.
            mover.observe_peer_barrier(_from_wire_cell(cop_turn.get("barrier_placed")))
            rule = mover.self_capture_check()
            if rule is not None:
                final_step = step + 1
                concession = {"claim": _to_wire_cell(mover.pos), "caught": True}
                final_payload = {
                    "step": final_step,
                    "role": role,
                    "sub_game": sub_game,
                    "position": _to_wire_cell(mover.pos),
                    "move": "STAY",
                    "intent": "truth",
                }
                final_nonce = secrets.token_hex(16)
                final_turn, final_record = build_turn(
                    record_payload=final_payload,
                    nonce=final_nonce,
                    sender=role,
                    hint="",
                    smell_grid=mover.our_smell_grid(),
                    barrier_placed=None,
                    claim_response=concession,
                    win_claim=None,
                )
                await out_session.send_turn(final_turn, final_record)
                print(
                    f"[match] sg{sub_game} thief self-detected {rule} capture at "
                    f"step {step} — conceding (cell {mover.pos})"
                )
                captured = True
                break

    await out_session.send_audit(role, "capture" if captured else "timeout")
    import contextlib

    with contextlib.suppress(Exception):
        await out_session.send_control(
            {
                "kind": "done",
                "sender": role,
                "sub_game_number": sub_game,
                "status": "complete",
                "step_budget": float(max_steps),
                "payload": {},
            }
        )
    their_audit = await _poll_deque(
        in_session.audits, timeout=_t("audit_poll_sec", 300.0), label="audit"
    )
    ok, errors = verify_audit(their_audit, dict(in_session.turns.played))
    in_session.turns = ReferenceV3Inbox(window=_t("reorder_window", 4))  # reset for next sub-game
    distinct = len(set(rl_moves))
    outcome = "capture" if captured else "survival"
    ended_at = datetime.now(UTC).isoformat()
    print(
        f"[match] sg{sub_game} audit ok={ok} errors={errors[:2]} outcome={outcome} "
        f"rl_moves={len(rl_moves)} distinct={distinct} sample={rl_moves[:8]}"
    )
    # Collect the sealed history for the log/result artifacts.
    our_records = [
        {"commit": r.get("commit"), "nonce": r.get("nonce"), "payload": r.get("payload")}
        for r in out_session.local_records
    ]
    declared = {
        t.get("step"): {
            "barrier_placed": t.get("barrier_placed"),
            "capture_claim": t.get("capture_claim"),
            "hint": t.get("hint"),
        }
        for t in in_session.turn_messages
    }
    opp_records = [
        {
            "commit": rec.get("commit"),
            "declared": declared.get((rec.get("payload") or {}).get("step"), {}),
            "nonce": rec.get("nonce"),
            "payload": rec.get("payload"),
        }
        for rec in (their_audit.get("records") or [])
    ]
    # Mutual step-0 audit: their sealed step_zero must declare the same github_commit as
    # their negotiate identity (else they equivocated between handshake and audit).
    # Audit-time refinement of a settled caught=true: the conceded/answered cell must be
    # where the thief's REVEALED trail actually ends. Degradation contract (SPEC §3.1):
    # a peer whose payloads carry no parseable position is fully conforming — note, never
    # accuse; only a parseable trail that contradicts the cell marks the capture disputed.
    if (
        captured
        and role == "police"
        and disputed_capture is None
        and settled_caught_cell is not None
    ):
        _trail = [
            (int(p["step"]), list(p["position"]))
            for p in ((r.get("payload") or {}) for r in opp_records)
            if isinstance(p.get("step"), int)
            and p.get("step") >= 1
            and isinstance(p.get("position"), (list, tuple))
            and len(p.get("position")) == 2
        ]
        if _trail and list(max(_trail)[1]) != list(settled_caught_cell):
            disputed_capture = {
                "cell": list(settled_caught_cell),
                "kind": "trail_end_mismatch",
                "revealed_final": list(max(_trail)[1]),
            }
            print(
                f"[match] sg{sub_game} audit: caught cell {settled_caught_cell} does not "
                f"end the revealed trail (final={max(_trail)[1]}) — recording disputed"
            )
    opp_sz = next(
        (
            r.get("payload")
            for r in opp_records
            if (r.get("payload") or {}).get("type") == "step_zero"
        ),
        None,
    )
    sz_mismatch = None
    if opp_sz is not None:
        declared_commit = opp_identity.get("github_commit")
        sealed_commit = opp_sz.get("github_commit")
        if declared_commit and sealed_commit and declared_commit != sealed_commit:
            sz_mismatch = {"declared": declared_commit, "sealed": sealed_commit}
    summary = {
        "audit": "Verified OK" if ok else "FAILED",
        "outcome": outcome,
        "digest_match": None,
        "disputed_capture": disputed_capture,
        "turns_completed": len(rl_moves),
        "steps_sealed": len(our_records),
        "opponent_step_zero": opp_sz,
        "step_zero_mismatch": sz_mismatch,
        "started_at": started_at,
        "ended_at": ended_at,
        "role": role,
        "group_id": "vibecode",
        "opponent_group_id": opponent_group_hint,
    }
    return {
        "sub_game": sub_game,
        "role": role,
        "audit_ok": ok,
        "outcome": outcome,
        "rl_move_count": len(rl_moves),
        "distinct_moves": distinct,
        "our_records": our_records,
        "opp_records": opp_records,
        "summary": summary,
        "started_at": started_at,
        "ended_at": ended_at,
        "our_commit": our_commit,
        "opp_identity": opp_identity,
        "opponent_group": negotiated.opponent_group,
    }


def _latest_turn(in_session, step: int) -> dict:
    for t in reversed(in_session.turn_messages):
        if int(t.get("step", -1)) == step:
            return t
    return {}


# ---------------------------------------------------------------------------
# Self-test harness: play vs the local sparring peer.
# ---------------------------------------------------------------------------
async def _self_test(
    role: str,
    sub_games: int,
    our_port: int,
    sparring_port: int,
    kit: Path,
    scent_model: str = "multiplicative_book_v1",
    move_policy: str = "rl",
) -> dict:
    from fastmcp import Client, FastMCP
    from fastmcp.client.transports import StreamableHttpTransport

    from cop_worker.protocol.pipeline import discover_reference_v3
    from cop_worker.protocol.reference_v3 import (
        default_terms,
        register_reference_v3_tools,
    )

    host = "127.0.0.1"
    our_url = f"http://{host}:{our_port}/mcp"
    sparring_url = f"http://{host}:{sparring_port}"
    # Sparring default setting is "Haifa"; match it for the self-test.
    terms = default_terms({"setting": "Haifa"})
    # Sparring takes the OPPOSITE role in sub-game 1.
    sparring_role = "police" if role == "thief" else "thief"

    in_session = _wire_session_class()(
        lambda t, p: (_ for _ in ()).throw(RuntimeError(f"no outbound on server ({t})"))
    )
    app = FastMCP(name="vibecode-match")
    register_reference_v3_tools(app, in_session)
    server_task = asyncio.create_task(
        app.run_async(transport="http", host=host, port=our_port, show_banner=False)
    )
    await _wait_port(host, our_port, timeout=15.0)
    print(f"[match] our reference-v3 server ready at {our_url} (role={role})")

    sparring = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "sparring.cli",
            "serve",
            "--role",
            sparring_role,
            "--scent-model",
            scent_model,
            "--port",
            str(sparring_port),
            "--host",
            host,
            "--peer",
            our_url,
            "--group-id",
            "sparring-match",
            "--await-peer",
        ],
        cwd=kit,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    results = []
    try:
        await _wait_port(host, sparring_port, timeout=30.0)
        await asyncio.sleep(2.0)
        transport = StreamableHttpTransport(f"{sparring_url}/mcp")
        async with Client(transport) as client:

            def _caller(c):
                async def _call(tool: str, params: dict) -> dict:
                    r = await c.call_tool(tool, params)
                    if not r.content:
                        return {"ok": getattr(r, "is_error", False) is not True}
                    val = getattr(r.content[0], "text", str(r.content[0]))
                    try:
                        parsed = _json.loads(val)
                    except (ValueError, TypeError):
                        return {"ok": True, "raw": val}
                    return parsed if isinstance(parsed, dict) else {"ok": True}

                return _call

            _profile, out_session = await discover_reference_v3(
                sparring_url, tool_caller=_caller(client)
            )
            other = {"police": "thief", "thief": "police"}
            for sg in range(1, sub_games + 1):
                # Roles alternate every sub-game; our sub-game-1 role is `role`.
                sg_role = role if sg % 2 == 1 else other[role]
                results.append(
                    await _play_subgame(
                        out_session,
                        in_session,
                        role=sg_role,
                        sub_game=sg,
                        group_id="vibecode",
                        group_name="vibecode",
                        terms=terms,
                        opponent_group_hint="sparring-match",
                        scent_model=scent_model,
                        move_policy=move_policy,
                    )
                )
    finally:
        server_task.cancel()
        import contextlib

        with contextlib.suppress(asyncio.CancelledError, Exception):
            await server_task
        sparring.terminate()
        with contextlib.suppress(Exception):
            sparring.wait(timeout=8)
    return {"role": role, "sub_games": results}


async def _play_match(
    *,
    opp_cop_url: str,
    opp_thief_url: str,
    our_cop_port: int,
    our_thief_port: int,
    opponent_group: str,
    setting: str,
    sub_games: int,
    members: list | None = None,
    our_counted: int = 0,
    scent_model: str = "multiplicative_book_v1",
    move_policy: str = "rl",
) -> dict:
    """Real match vs a live peer over reference-v3, role-split, RL moves.

    We alternate: thief on odd sub-games (peer is cop → dial its cop URL), police on
    even (peer is thief → dial its thief URL). We serve both our endpoints so the peer
    can dial the active one; moves come from the trained RL policy.
    """
    from fastmcp import Client, FastMCP
    from fastmcp.client.transports import StreamableHttpTransport

    from cop_worker.protocol.pipeline import discover_reference_v3
    from cop_worker.protocol.reference_v3 import (
        default_terms,
        register_reference_v3_tools,
    )

    host = "0.0.0.0"
    terms = default_terms({"setting": setting})
    sessions, apps, tasks = {}, {}, []
    # Port-free preflight: a stray process from an earlier attempt holding our port would
    # silently swallow the peer's traffic (our run_async fails in its task while the stray
    # socket answers _wait_port). Refuse loudly instead — WARNINGS §5.
    for _pname, _p in (("cop", our_cop_port), ("thief", our_thief_port)):
        if _check_port("127.0.0.1", _p):
            raise RuntimeError(
                f"port {_p} (our {_pname} endpoint) is already in use — a stray process "
                f"from a previous attempt would swallow this match; kill it first"
            )

    def _caller(client):
        async def _call(tool: str, params: dict) -> dict:
            # At-least-once with the 10s cap, routed through the central outbound
            # gateway (rate pacing + bounded retries). Retries are dedup-safe by
            # design: turns dedupe on commit, duplicate greetings are drained, and a
            # re-sent audit re-carries identical records (imreeyal §3.15 tolerates
            # duplicates; equivocation, not repetition, is the refusal).
            from cop_worker.net_gateway import GATEWAY

            r = await GATEWAY.call(
                "mcp",
                lambda: client.call_tool(tool, params),
                retries=int(_t("mcp_call_retries", 6)),
                backoff_s=0.5,
                max_backoff_s=5.0,
                label=tool,
            )
            if not r.content:
                return {"ok": getattr(r, "is_error", False) is not True}
            val = getattr(r.content[0], "text", str(r.content[0]))
            try:
                parsed = _json.loads(val)
            except (ValueError, TypeError):
                return {"ok": True, "raw": val}
            return parsed if isinstance(parsed, dict) else {"ok": True}

        return _call

    # Serve both our reference-v3 endpoints (cop + thief), one inbound session each.
    _Session = _wire_session_class()
    for role_name, port in (("police", our_cop_port), ("thief", our_thief_port)):
        sess = _Session(lambda t, p: (_ for _ in ()).throw(RuntimeError(f"no outbound ({t})")))
        app = FastMCP(name=f"vibecode-{role_name}")
        register_reference_v3_tools(app, sess)
        sessions[role_name] = sess
        apps[role_name] = app
        tasks.append(
            asyncio.create_task(
                app.run_async(transport="http", host=host, port=port, show_banner=False)
            )
        )
    await _wait_port("127.0.0.1", our_cop_port, timeout=15.0)
    await _wait_port("127.0.0.1", our_thief_port, timeout=15.0)
    print(f"[match] serving cop:{our_cop_port} thief:{our_thief_port} vs {opponent_group}")

    results = []
    # The opponent group we may DECLARE a game_uid for: seeded from configuration (a real
    # pairing names its opponent in runtime.toml), confirmed/learned from the first
    # verified greeting. Self-test passes a placeholder hint, so require an exact match
    # to what negotiation later verifies before trusting a seed for sub-game 1.
    confirmed_group: str | None = (
        opponent_group if opponent_group and not opponent_group.startswith("sparring") else None
    )
    try:
        sg = 1
        # Index-hold budget: while it lasts, a window in which no game happened is
        # RETRIED at the same sub-game number instead of spending it (uoh-sqak
        # convergence rule). None = not yet started timing this index.
        hold_deadline: float | None = None
        while sg <= sub_games:
            our_role = "thief" if sg % 2 == 1 else "police"
            peer_url = opp_cop_url if our_role == "thief" else opp_thief_url
            mcp_url = peer_url if peer_url.endswith("/mcp") else peer_url.rstrip("/") + "/mcp"
            base_url = mcp_url.removesuffix("/mcp")  # discover probes transports off the base
            in_session = sessions[our_role]
            if hold_deadline is None:
                hold_deadline = time.monotonic() + _t("subgame_hold_sec", 300.0)
            # Wait ONLY for the endpoint this sub-game must dial (peer binds per-window).
            print(f"[match] sg{sg} ({our_role}) — awaiting peer endpoint {mcp_url}")
            if not await _await_endpoint(mcp_url, Client, window_s=_t("endpoint_await_sec", 900.0)):
                print(f"[match] sg{sg} peer window never opened — recording skip, continuing")
                results.append(
                    {
                        "sub_game": sg,
                        "role": our_role,
                        "audit_ok": False,
                        "error": "peer_window_never_opened",
                    }
                )
                sg += 1
                hold_deadline = None
                continue
            # Play once its window is open. A transient failure records the sub-game and
            # moves on — it never crashes the whole series (their windows re-run).
            try:
                transport = StreamableHttpTransport(mcp_url)
                # Per-call cap STRICTLY below the signed response_timeout_sec (30): the MCP
                # SDK's unset default leaves a 300s read ceiling, so one delivered-but-
                # unanswered push could breach a signed deadline while every call "looks
                # fine" (imreeyal §3.5). 10s matches the proven league configuration.
                call_cap = _t("mcp_call_sec", 10.0)
                if call_cap >= float(terms.get("response_timeout_sec", 30) or 30):
                    raise RuntimeError(
                        f"mcp_call_sec={call_cap} must be strictly below the signed "
                        f"response timeout; refusing to start"
                    )
                async with Client(transport, timeout=call_cap) as client:
                    # Generous probe/introspect deadlines: a tunnelled peer is slower
                    # than the 5s default, which otherwise fails discovery spuriously.
                    try:
                        _profile, out_session = await discover_reference_v3(
                            base_url,
                            tool_caller=_caller(client),
                            probe_timeout_s=_t("probe_sec", 30.0),
                            introspect_timeout_s=_t("introspect_sec", 30.0),
                        )
                    except Exception as exc:
                        # Discovery precedes the handshake: certainly no game yet.
                        raise NoGameHappened(
                            f"discovery failed: {type(exc).__name__}: {str(exc)[:120]}"
                        ) from exc
                    sg_result = await _play_subgame(
                        out_session,
                        in_session,
                        role=our_role,
                        sub_game=sg,
                        group_id="vibecode",
                        group_name="vibecode",
                        terms=terms,
                        opponent_group_hint=opponent_group,
                        members=members,
                        our_counted=our_counted,
                        scent_model=scent_model,
                        move_policy=move_policy,
                        declared_opponent_group=confirmed_group,
                    )
                    results.append(sg_result)
                    # Learned from a VERIFIED handshake: declare the uid from sg2 onward.
                    if sg_result.get("opponent_group"):
                        confirmed_group = sg_result["opponent_group"]
                print(f"[match] sg{sg} complete")
            except NoGameHappened as exc:
                # No game happened in this window (discovery / handshake / zero-turn
                # failure): HOLD the index and retry so a peer that holds-and-converges
                # can land on it, bounded by wall-clock — never by attempts. Only an
                # exhausted budget spends the number (files the row, moves on).
                if any(r.get("sub_game") == sg and r.get("audit_ok") for r in results):
                    # Settled rows are sacred: never replay a settled index.
                    print(f"[match] sg{sg} post-settlement noise — benign, continuing")
                    sg += 1
                    hold_deadline = None
                    continue
                if time.monotonic() < hold_deadline:
                    print(
                        f"[match] sg{sg} no game happened "
                        f"({str(exc)[:110]}) — HOLDING index, retrying"
                    )
                    await asyncio.sleep(2.0)
                    continue
                print(
                    f"[match] sg{sg} no game happened and hold budget exhausted "
                    f"({str(exc)[:90]}) — recording, continuing"
                )
                results.append(
                    {
                        "sub_game": sg,
                        "role": our_role,
                        "audit_ok": False,
                        "error": f"no_game_happened: {str(exc)[:180]}",
                    }
                )
                sg += 1
                hold_deadline = None
                continue
            except Exception as exc:
                # A peer that exits its per-window process AFTER settlement (imreeyal's
                # design) makes our client teardown raise — after the verified audit.
                # Recording that as a failure row double-counted a settled window
                # (STATUS read 6/12 and the 6/6 report guard refused a clean series —
                # live finding, 2026-08-10 friendly). A settled sub-game absorbs its
                # teardown noise; only a genuinely unsettled one records the error.
                if any(r.get("sub_game") == sg and r.get("audit_ok") for r in results):
                    print(
                        f"[match] sg{sg} teardown noise after settlement "
                        f"({type(exc).__name__}: {str(exc)[:80]}) — benign, continuing"
                    )
                    sg += 1
                    hold_deadline = None
                    continue
                print(
                    f"[match] sg{sg} failed ({type(exc).__name__}: {str(exc)[:110]}) — continuing"
                )
                results.append(
                    {
                        "sub_game": sg,
                        "role": our_role,
                        "audit_ok": False,
                        "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                    }
                )
                sg += 1
                hold_deadline = None
                continue
            sg += 1
            hold_deadline = None
    finally:
        for t in tasks:
            t.cancel()
        import contextlib

        for t in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
    return {"opponent": opponent_group, "sub_games": results}


def _write_result(result: dict) -> Path:
    out_dir = REPO_ROOT / "reports" / "ref3_matches"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "last_match_result.json"
    path.write_text(_json.dumps(result, indent=2), encoding="utf-8")
    return path


def _git_head(repo: Path) -> str:
    import subprocess

    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        return out or "unknown"
    except Exception:
        return "unknown"


def _emit_artifacts(result: dict, args) -> None:
    """Write the four league artifacts to the repo; email ONLY the result."""
    from ref3_artifacts import (
        build_config,
        build_declaration,
        build_log,
        build_result,
        email_result,
        score_series,
        update_counted_ledger,
        write_artifact,
    )

    from cop_worker.protocol.reference_v3 import (
        default_terms,
        derive_game_id,
        derive_game_uid,
    )

    opp = args.opponent_group
    # Save the exact config used to play this opponent: config/opponents/<opp>/{game.json,
    # runtime.toml}. An auditable record + a reusable profile selectable next time via --config.
    try:
        import shutil

        prof = REPO_ROOT / "config" / "opponents" / opp
        prof.mkdir(parents=True, exist_ok=True)
        for f in ("game.json", "runtime.toml"):
            src = REPO_ROOT / "config" / f
            # NEVER overwrite an existing profile file: the base copy lacks the
            # profile's own keys ([protocol] scent_model/move_policy, opponent URLs) —
            # the auto-save clobbered the imreeyal profile with anrbj666 defaults
            # (live finding, 2026-08-10 friendly; restored from git).
            if src.is_file() and not (prof / f).exists():
                shutil.copyfile(src, prof / f)
        print(
            f"[match] saved config profile used vs {opp} -> config/opponents/{opp}/ "
            f"(existing profile files preserved)"
        )
    except Exception as exc:
        print(f"[match] WARN could not save opponent config ({type(exc).__name__}: {exc})")
    game_id = derive_game_id("vibecode", opp)
    game_uid = derive_game_uid(default_terms({"setting": args.setting}), "vibecode", opp)
    cop_commit = _git_head(REPO_ROOT)
    results_dir = REPO_ROOT / "results"
    config_dir = REPO_ROOT / "config" / "games"
    played = [sg for sg in result["sub_games"] if sg.get("our_records") is not None]
    for sg in played:
        n = sg["sub_game"]
        write_artifact(
            build_config(game_id, game_uid, n, args.setting, opp),
            config_dir / f"config_{game_id}_g{n:02d}.json",
        )
        write_artifact(
            build_log(
                game_id,
                game_uid,
                n,
                sg["role"],
                opp,
                sg["our_records"],
                sg["opp_records"],
                sg["summary"],
            ),
            results_dir / f"log_{game_id}_g{n:02d}.json",
        )
    # The opponent's declared identity (rules 49/53) — repos, counted count — from their greeting.
    opp_ids = [sg.get("opp_identity") or {} for sg in played if sg.get("opp_identity")]
    opp_repos = next((i.get("repos") for i in opp_ids if i.get("repos")), {})
    opp_counted = next(
        (
            i.get("counted_games_played")
            for i in opp_ids
            if i.get("counted_games_played") is not None
        ),
        0,
    )
    our_counted = getattr(args, "counted_played", 0)
    counted = getattr(args, "counted", False)
    rows, final_result = score_series(
        played, opp, game_id, our_played=our_counted, opp_played=opp_counted, counted=counted
    )
    members = [m.strip() for m in args.members.split(",") if m.strip()]
    starts = [sg.get("started_at", "") for sg in played]
    ends = [sg.get("ended_at", "") for sg in played]
    thief_commit = _git_head(REPO_ROOT.parent / "vibecode-thief")
    write_artifact(
        build_declaration(
            game_id,
            game_uid,
            opp,
            members,
            cop_commit,
            starts[0] if starts else "",
            ends[-1] if ends else "",
            opp_identity=(opp_ids[0] if opp_ids else None),
            our_counted=our_counted,
            thief_commit=thief_commit,
        ),
        results_dir / f"declaration_{game_id}.json",
    )
    result_obj = build_result(game_id, game_uid, opp, rows, final_result, opp_repos=opp_repos)
    write_artifact(result_obj, results_dir / f"result_{game_id}.json")
    print(
        f"[match] artifacts: {len(played)}x(config+log) + declaration + result "
        f"under results/ and config/games/"
    )
    print(f"[match] result: {final_result['total_score']} winner={final_result['winner_group']}")
    # Settlement guard: a report is filed ONLY when the WHOLE series settled — all six windows
    # played AND each audit "Verified OK". A partial/failed series never auto-files a broken or
    # empty result to the league (matches anrbj666's runner). Re-run the missing windows, then
    # report. Artifacts are always kept locally regardless.
    EXPECTED_SUB_GAMES = 6
    n_settled = sum(1 for sg in played if sg.get("audit_ok"))
    series_complete = len(played) == EXPECTED_SUB_GAMES and n_settled == EXPECTED_SUB_GAMES
    mid = None
    if not series_complete:
        print(
            f"[match] REPORT WITHHELD (settlement guard): series not fully settled — "
            f"{n_settled}/{EXPECTED_SUB_GAMES} Verified OK, {len(played)}/{EXPECTED_SUB_GAMES} "
            f"windows played. No email, no ledger entry. Artifacts kept locally; re-run the "
            f"missing/failed windows before reporting."
        )
    elif not args.no_email:
        try:
            token = REPO_ROOT / "secrets" / "gmail" / "token.json"
            mid = email_result(result_obj, args.report_to, f"result_{game_id}.json", token)
            print(f"[match] emailed result ONLY to {args.report_to} (id={mid})")
        except Exception as exc:
            print(f"[match] email FAILED ({type(exc).__name__}: {str(exc)[:140]})")
    # League ledger: record ONLY a fully-settled counted series (rules 37-38, the counted tracker).
    if counted and series_complete:
        ledger = update_counted_ledger(
            results_dir / "counted_series.json",
            game_id=game_id,
            game_uid=game_uid,
            opponent=opp,
            result_obj=result_obj,
            message_id=mid,
            our_counted_before=our_counted,
        )
        print(
            f"[match] counted ledger updated: counted_games_played={ledger['counted_games_played']} "
            f"(results/counted_series.json)"
        )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test", action="store_true", help="Play vs the local sparring peer")
    p.add_argument("--role", choices=["police", "thief"], default="police")
    p.add_argument("--sub-games", type=int, default=1)
    p.add_argument("--our-port", type=int, default=5011)
    p.add_argument("--sparring-port", type=int, default=8941)
    p.add_argument("--kit-root", type=Path, default=KIT_ROOT)
    # Config profile selection: --config <name|dir> picks config/opponents/<name>/ (else base
    # config/). CLI flags below always override the profile's values (defaults are None so we
    # can tell "unset" from an explicit value).
    p.add_argument(
        "--config",
        default=None,
        help="Config profile: a name under config/opponents/, or a directory",
    )
    # Real-match args:
    p.add_argument("--match", action="store_true", help="Play a live peer over reference-v3")
    p.add_argument("--opp-cop-url", help="Opponent cop MCP URL (dialed when we are thief)")
    p.add_argument("--opp-thief-url", help="Opponent thief MCP URL (dialed when we are cop)")
    p.add_argument("--opponent-group", default=None)
    p.add_argument("--our-cop-port", type=int, default=None)
    p.add_argument("--our-thief-port", type=int, default=None)
    p.add_argument("--setting", default=None)
    # Result recipient. Default = OUR OWN inbox (never the league address). The counted/league
    # address is passed explicitly at run time for a counted game only.
    p.add_argument("--report-to", default=None)
    p.add_argument("--no-email", action="store_true", help="Skip emailing the result")
    p.add_argument(
        "--members", default=None, help="Comma-separated member names for the declaration"
    )
    # Counted-game accounting (rules 37-38): friendly = counted=False (no increment).
    p.add_argument("--counted", action="store_true", help="Mark this as a COUNTED series")
    p.add_argument(
        "--counted-played",
        type=int,
        default=None,
        help="Our prior counted-games count (for games_played_including_this)",
    )
    p.add_argument(
        "--scent-model",
        default=None,
        choices=("multiplicative_book_v1", "subtractive_chebyshev_v1"),
        help="Locked scent model for this pairing (default: [protocol] in runtime.toml)",
    )
    p.add_argument(
        "--move-policy",
        default=None,
        choices=("rl", "hybrid_search", "hybrid_search_belief"),
        help="Move engine: plain RL, or minimax-over-exact-tracking with RL fallback",
    )
    args = p.parse_args()

    # Resolve config profile and fill any unset args from runtime.toml (CLI wins).
    from cop_worker.config_loader import load_config

    cfg = load_config(args.config)
    rt = cfg["runtime"]
    apply_runtime_config(rt)
    net, ident, rep = rt.get("network", {}), rt.get("identity", {}), rt.get("report", {})
    if args.opp_cop_url is None:
        args.opp_cop_url = net.get("opp_cop_url")
    if args.opp_thief_url is None:
        args.opp_thief_url = net.get("opp_thief_url")
    if args.opponent_group is None:
        args.opponent_group = net.get("opponent_group", "anrbj666")
    if args.our_cop_port is None:
        args.our_cop_port = int(net.get("our_cop_port", 61224))
    if args.our_thief_port is None:
        args.our_thief_port = int(net.get("our_thief_port", 61223))
    if args.setting is None:
        args.setting = cfg["game"].get("world", {}).get("map_area", "New York")
    if args.report_to is None:
        args.report_to = rep.get("recipient", "agentsorch@gmail.com")
    if args.members is None:
        args.members = ",".join(ident.get("members", ["Ron Marom", "Amit Kuperminz"]))
    if args.counted_played is None:
        args.counted_played = int(rt.get("counted", {}).get("counted_played", 0))
    if args.scent_model is None:
        args.scent_model = rt.get("protocol", {}).get("scent_model", "multiplicative_book_v1")
    if args.move_policy is None:
        args.move_policy = rt.get("protocol", {}).get("move_policy", "rl")
    # One switch, everywhere: the locked model drives our wire emission (RLMover), our
    # Step-0 declaration (build_negotiation), the peer-frame diagnostic, AND any policy/
    # obs-mode code that reads COPTHIEF_SCENT_MODEL — set the env before policies load.
    import os as _os

    _os.environ["COPTHIEF_SCENT_MODEL"] = args.scent_model
    print(
        f"[match] config profile: {cfg['source']} ({cfg['profile_dir']}) "
        f"scent_model={args.scent_model}"
    )

    if args.match:
        if not (args.opp_cop_url and args.opp_thief_url):
            print("ERROR: --match requires --opp-cop-url and --opp-thief-url (CLI or runtime.toml)")
            return 2
        _install_match_log(args.opponent_group or "unknown")
        members = [m.strip() for m in args.members.split(",") if m.strip()]
        result = asyncio.run(
            _play_match(
                opp_cop_url=args.opp_cop_url,
                opp_thief_url=args.opp_thief_url,
                our_cop_port=args.our_cop_port,
                our_thief_port=args.our_thief_port,
                opponent_group=args.opponent_group,
                setting=args.setting,
                sub_games=args.sub_games if args.sub_games > 1 else 6,
                members=members,
                our_counted=args.counted_played,
                scent_model=args.scent_model,
                move_policy=args.move_policy,
            )
        )
        _write_result(result)  # raw internal snapshot (debug)
        oks = [sg for sg in result["sub_games"] if sg.get("audit_ok")]
        print(f"\n[match] STATUS: audits {len(oks)}/{len(result['sub_games'])} ok")
        _emit_artifacts(result, args)
        return 0 if oks and len(oks) == len(result["sub_games"]) else 1

    if not args.self_test:
        print("Use --self-test (vs sparring) or --match --opp-cop-url ... --opp-thief-url ...")
        return 2
    kit = args.kit_root.resolve()
    if not (kit / "verify_vectors.py").is_file():
        print(f"ERROR: not a league-protocol clone: {kit}")
        return 1
    _install_match_log("selftest")
    result = asyncio.run(
        _self_test(
            args.role,
            args.sub_games,
            args.our_port,
            args.sparring_port,
            kit,
            scent_model=args.scent_model,
            move_policy=args.move_policy,
        )
    )
    print("\n[match] RESULT:", _json.dumps(result, indent=2))
    oks = [sg for sg in result["sub_games"] if sg.get("audit_ok")]
    sgs = result["sub_games"]
    rl_ok = all(sg["distinct_moves"] > 1 for sg in sgs) if sgs else False
    print(
        f"[match] STATUS: audits {len(oks)}/{len(result['sub_games'])} ok; RL-varied-moves={rl_ok}"
    )
    return 0 if oks and rl_ok else 1


if __name__ == "__main__":
    sys.exit(main())
