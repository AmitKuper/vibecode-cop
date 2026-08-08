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

# Cop barrier placement: target cell = own_position + delta (mirrors domain/transition.py).
_PLACE_DELTAS = {"PLACE_N": (0, -1), "PLACE_S": (0, 1), "PLACE_E": (1, 0), "PLACE_W": (-1, 0)}


# ---------------------------------------------------------------------------
# RL move engine — the whole point: real policy, not random.
# ---------------------------------------------------------------------------
class RLMover:
    """Wraps the trained role policy and tracks own position + emitted scent."""

    def __init__(self, role: str, terms: dict) -> None:
        from cop_worker.board import Board
        from cop_worker.rl.action_space import COP_ACTIONS, THIEF_ACTIONS
        from cop_worker.rl.recurrent_policy import load_recurrent_policy

        self.role = role  # "police" (cop) or "thief"
        self.terms = terms
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
        self.policy = load_recurrent_policy(manifest, manifest_role)
        start = terms["cop_start"] if role == "police" else terms["thief_start"]
        self.pos = [int(start[0]), int(start[1])]  # [x, y]
        # Cop barrier state (thief never places): quota, placed cells, last placement.
        self.barriers_remaining = int(terms.get("barriers_max", 0)) if role == "police" else 0
        self.barriers: list[list[int]] = []
        self.last_barrier: list[int] | None = None
        # A board whose "thief" cell we drive to OUR position, so update_scent emits
        # the byte-exact book field around us regardless of role.
        self._board = Board(
            cop_position=[0, 0], thief_position=list(self.pos), grid_size=self.grid
        )
        from cop_worker.rules_engine import RulesEngine

        self._rules = RulesEngine(self._board, max_turns=terms["max_steps"])

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
        action = self.policy.select_action(obs, belief, list(self.actions))
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

    def our_smell_grid(self) -> dict:
        """Byte-exact book scent around our own position, as the wire {'r,c': v}."""
        self._board.thief_position = list(self.pos)  # emitter = us
        self._rules.update_scent()
        field = self._rules.get_scent_field()
        n = self.grid
        return {f"{r},{c}": field[r][c] for r in range(n) for c in range(n) if field[r][c] > 0.0}


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
    raise TimeoutError(f"timeout waiting for negotiate matching sub_game {sub_game}")


async def _poll_turn(inbox, step: int, *, timeout: float) -> dict:
    """Wait until the inbox has the opponent's turn for `step`; return it."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if step in inbox.played or inbox.next_step > step:
            return inbox.turn_for(step) if hasattr(inbox, "turn_for") else {}
        await asyncio.sleep(0.05)
    raise TimeoutError(f"timeout waiting for opponent turn step {step}")


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
                print(f"[match] waiting for peer endpoint {mcp_url} "
                      f"({type(exc).__name__}: {str(exc)[:80]})")
                announced = True
            await asyncio.sleep(8)
    return False


# ---------------------------------------------------------------------------
# One sub-game over the reference-v3 wire, driven by the RL policy.
# ---------------------------------------------------------------------------
async def _play_subgame(out_session, in_session, *, role: str, sub_game: int,
                        group_id: str, group_name: str, terms: dict,
                        opponent_group_hint: str) -> dict:
    from cop_worker.protocol.reference_v3 import (
        ReferenceV3Inbox,
        build_negotiation,
        build_turn,
        verify_audit,
        verify_negotiation,
    )

    max_steps = terms["max_steps"]
    # Fresh per-sub-game state: sealed records and the inbox must never leak across
    # sub-games (else step 1 of the next sub-game equivocates against the last one).
    out_session.local_records = []
    out_session._local_records_by_step = {}
    in_session.turns = ReferenceV3Inbox(window=4)
    in_session.turn_messages.clear()
    in_session.expected_turn_sender = None
    in_session.audits.clear()      # drain stale end-of-game payloads from prior sub-games
    in_session.controls.clear()
    from datetime import datetime
    started_at = datetime.now(UTC).isoformat()
    nonce = secrets.token_hex(16)
    greeting = build_negotiation(
        terms=terms, nonce=nonce, group_id=group_id, group_name=group_name,
        role=role, sub_game_number=sub_game,
    )
    await out_session.send_negotiation(greeting)
    # Match the greeting by sub_game_number (not FIFO) — the peer's re-dials pile up.
    theirs = await _poll_agreement(in_session.agreements, sub_game, timeout=300.0)
    print(f"[match] sg{sub_game} peer greeting sub_game={theirs.get('sub_game_number')} "
          f"role={theirs.get('role')}")
    negotiated = verify_negotiation(greeting, theirs)
    print(f"[match] sg{sub_game} role={role} handshake OK vs {negotiated.opponent_group} "
          f"uid={negotiated.game_uid[:12]}")

    mover = RLMover(role, terms)
    we_move_first = (role == "thief")  # reference-v3: THIEF moves first every sub-game
    rl_moves: list[str] = []
    pending_answer: dict | None = None  # thief's answer to a cop capture_claim (rides next turn)
    captured = False  # True if this sub-game ended in a capture (either direction)

    for step in range(1, max_steps + 1):
        if not we_move_first:
            # cop: wait for the thief's sealed turn first, absorb its scent/hint.
            await _poll_turn(in_session.turns, step, timeout=120.0)
            opp = _latest_turn(in_session, step)
            # Thief concedes our capture (barrier on its cell / claim) via caught=true.
            if (opp.get("claim_response") or {}).get("caught") is True:
                print(f"[match] sg{sub_game} thief conceded capture at step {step}")
                captured = True
                break
        else:
            opp = _latest_turn(in_session, step)

        action = mover.decide(step, sub_game, opp.get("smell_grid", {}), opp.get("hint", ""))
        rl_moves.append(action)
        mover.apply(action)
        record_payload = {
            "step": step, "role": role, "sub_game": sub_game,
            "position": list(mover.pos), "move": action, "intent": "truth",
        }
        if mover.last_barrier is not None:
            record_payload["barrier_placed"] = mover.last_barrier
        # A pending capture-claim answer (thief only) rides this turn; caught => terminal.
        answer, pending_answer = pending_answer, None
        caught = bool(answer and answer.get("caught"))
        step_nonce = secrets.token_hex(16)
        # Survival terminal on the thief's final step (unless it's a caught answer);
        # the blind cop needs it or it waits out its budget (kit turnloop.py:183,303).
        win_claim = ({"type": "survival"}
                     if (role == "thief" and step == max_steps and not caught) else None)
        turn, record = build_turn(
            record_payload=record_payload, nonce=step_nonce, sender=role,
            hint=f"moving {action.lower()}", smell_grid=mover.our_smell_grid(),
            barrier_placed=mover.last_barrier, claim_response=answer, win_claim=win_claim,
        )
        await out_session.send_turn(turn, record)
        if caught:
            print(f"[match] sg{sub_game} our thief answered caught=true at step {step}")
            captured = True
            break
        if we_move_first and win_claim is None:
            # Thief waits for the cop's turn, then prepares an answer to any capture claim
            # it carries (rides our next turn — kit turnloop.py:271-273).
            await _poll_turn(in_session.turns, step, timeout=120.0)
            claim = _latest_turn(in_session, step).get("capture_claim")
            if claim is not None:
                pending_answer = {"claim": list(mover.pos),
                                  "caught": list(claim) == list(mover.pos)}

    await out_session.send_audit(role, "capture" if captured else "timeout")
    import contextlib
    with contextlib.suppress(Exception):
        await out_session.send_control({
            "kind": "done", "sender": role, "sub_game_number": sub_game,
            "status": "complete", "step_budget": float(max_steps), "payload": {},
        })
    their_audit = await _poll_deque(in_session.audits, timeout=300.0, label="audit")
    ok, errors = verify_audit(their_audit, dict(in_session.turns.played))
    in_session.turns = ReferenceV3Inbox(window=4)  # reset for next sub-game
    distinct = len(set(rl_moves))
    outcome = "capture" if captured else "survival"
    ended_at = datetime.now(UTC).isoformat()
    print(f"[match] sg{sub_game} audit ok={ok} errors={errors[:2]} outcome={outcome} "
          f"rl_moves={len(rl_moves)} distinct={distinct} sample={rl_moves[:8]}")
    # Collect the sealed history for the log/result artifacts.
    our_records = [{"commit": r.get("commit"), "nonce": r.get("nonce"), "payload": r.get("payload")}
                   for r in out_session.local_records]
    declared = {t.get("step"): {"barrier_placed": t.get("barrier_placed"),
                                "capture_claim": t.get("capture_claim"), "hint": t.get("hint")}
                for t in in_session.turn_messages}
    opp_records = [{"commit": rec.get("commit"),
                    "declared": declared.get((rec.get("payload") or {}).get("step"), {}),
                    "nonce": rec.get("nonce"), "payload": rec.get("payload")}
                   for rec in (their_audit.get("records") or [])]
    summary = {"audit": "Verified OK" if ok else "FAILED", "outcome": outcome,
               "digest_match": None, "disputed_capture": None,
               "turns_completed": len(rl_moves), "steps_sealed": len(our_records),
               "started_at": started_at, "ended_at": ended_at, "role": role,
               "group_id": "vibecode", "opponent_group_id": opponent_group_hint}
    return {"sub_game": sub_game, "role": role, "audit_ok": ok, "outcome": outcome,
            "rl_move_count": len(rl_moves), "distinct_moves": distinct,
            "our_records": our_records, "opp_records": opp_records, "summary": summary,
            "started_at": started_at, "ended_at": ended_at}


def _latest_turn(in_session, step: int) -> dict:
    for t in reversed(in_session.turn_messages):
        if int(t.get("step", -1)) == step:
            return t
    return {}


# ---------------------------------------------------------------------------
# Self-test harness: play vs the local sparring peer.
# ---------------------------------------------------------------------------
async def _self_test(role: str, sub_games: int, our_port: int,
                     sparring_port: int, kit: Path) -> dict:
    from fastmcp import Client, FastMCP
    from fastmcp.client.transports import StreamableHttpTransport

    from cop_worker.protocol.pipeline import discover_reference_v3
    from cop_worker.protocol.reference_v3 import (
        ReferenceV3Session,
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

    in_session = ReferenceV3Session(
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
        [sys.executable, "-m", "sparring.cli", "serve", "--role", sparring_role,
         "--scent-model", "multiplicative_book_v1", "--port", str(sparring_port),
         "--host", host, "--peer", our_url, "--group-id", "sparring-match", "--await-peer"],
        cwd=kit, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
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
                sparring_url, tool_caller=_caller(client))
            other = {"police": "thief", "thief": "police"}
            for sg in range(1, sub_games + 1):
                # Roles alternate every sub-game; our sub-game-1 role is `role`.
                sg_role = role if sg % 2 == 1 else other[role]
                results.append(await _play_subgame(
                    out_session, in_session, role=sg_role, sub_game=sg,
                    group_id="vibecode", group_name="vibecode",
                    terms=terms, opponent_group_hint="sparring-match",
                ))
    finally:
        server_task.cancel()
        import contextlib
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await server_task
        sparring.terminate()
        with contextlib.suppress(Exception):
            sparring.wait(timeout=8)
    return {"role": role, "sub_games": results}


async def _play_match(*, opp_cop_url: str, opp_thief_url: str, our_cop_port: int,
                      our_thief_port: int, opponent_group: str, setting: str,
                      sub_games: int) -> dict:
    """Real match vs a live peer over reference-v3, role-split, RL moves.

    We alternate: thief on odd sub-games (peer is cop → dial its cop URL), police on
    even (peer is thief → dial its thief URL). We serve both our endpoints so the peer
    can dial the active one; moves come from the trained RL policy.
    """
    from fastmcp import Client, FastMCP
    from fastmcp.client.transports import StreamableHttpTransport

    from cop_worker.protocol.pipeline import discover_reference_v3
    from cop_worker.protocol.reference_v3 import (
        ReferenceV3Session,
        default_terms,
        register_reference_v3_tools,
    )

    host = "0.0.0.0"
    terms = default_terms({"setting": setting})
    sessions, apps, tasks = {}, {}, []

    def _caller(client):
        async def _call(tool: str, params: dict) -> dict:
            r = await client.call_tool(tool, params)
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
    for role_name, port in (("police", our_cop_port), ("thief", our_thief_port)):
        sess = ReferenceV3Session(
            lambda t, p: (_ for _ in ()).throw(RuntimeError(f"no outbound ({t})"))
        )
        app = FastMCP(name=f"vibecode-{role_name}")
        register_reference_v3_tools(app, sess)
        sessions[role_name] = sess
        apps[role_name] = app
        tasks.append(asyncio.create_task(
            app.run_async(transport="http", host=host, port=port, show_banner=False)))
    await _wait_port("127.0.0.1", our_cop_port, timeout=15.0)
    await _wait_port("127.0.0.1", our_thief_port, timeout=15.0)
    print(f"[match] serving cop:{our_cop_port} thief:{our_thief_port} vs {opponent_group}")

    results = []
    try:
        for sg in range(1, sub_games + 1):
            our_role = "thief" if sg % 2 == 1 else "police"
            peer_url = opp_cop_url if our_role == "thief" else opp_thief_url
            mcp_url = peer_url if peer_url.endswith("/mcp") else peer_url.rstrip("/") + "/mcp"
            base_url = mcp_url.removesuffix("/mcp")  # discover probes transports off the base
            in_session = sessions[our_role]
            # Wait ONLY for the endpoint this sub-game must dial (peer binds per-window).
            print(f"[match] sg{sg} ({our_role}) — awaiting peer endpoint {mcp_url}")
            if not await _await_endpoint(mcp_url, Client, window_s=900.0):
                print(f"[match] sg{sg} peer window never opened — recording skip, continuing")
                results.append({"sub_game": sg, "role": our_role, "audit_ok": False,
                                "error": "peer_window_never_opened"})
                continue
            # Play once its window is open. A transient failure records the sub-game and
            # moves on — it never crashes the whole series (their windows re-run).
            try:
                transport = StreamableHttpTransport(mcp_url)
                async with Client(transport) as client:
                    # Generous probe/introspect deadlines: a tunnelled peer is slower
                    # than the 5s default, which otherwise fails discovery spuriously.
                    _profile, out_session = await discover_reference_v3(
                        base_url, tool_caller=_caller(client),
                        probe_timeout_s=30.0, introspect_timeout_s=30.0)
                    results.append(await _play_subgame(
                        out_session, in_session, role=our_role, sub_game=sg,
                        group_id="vibecode", group_name="vibecode", terms=terms,
                        opponent_group_hint=opponent_group))
                print(f"[match] sg{sg} complete")
            except Exception as exc:
                print(f"[match] sg{sg} failed "
                      f"({type(exc).__name__}: {str(exc)[:110]}) — continuing")
                results.append({"sub_game": sg, "role": our_role, "audit_ok": False,
                                "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
                continue
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
        out = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
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
        write_artifact,
    )

    from cop_worker.protocol.reference_v3 import (
        default_terms,
        derive_game_id,
        derive_game_uid,
    )
    opp = args.opponent_group
    game_id = derive_game_id("vibecode", opp)
    game_uid = derive_game_uid(default_terms({"setting": args.setting}), "vibecode", opp)
    cop_commit = _git_head(REPO_ROOT)
    results_dir = REPO_ROOT / "results"
    config_dir = REPO_ROOT / "config" / "games"
    played = [sg for sg in result["sub_games"] if sg.get("our_records") is not None]
    for sg in played:
        n = sg["sub_game"]
        write_artifact(build_config(game_id, game_uid, n, args.setting, opp),
                       config_dir / f"config_{game_id}_g{n:02d}.json")
        write_artifact(build_log(game_id, game_uid, n, sg["role"], opp, sg["our_records"],
                                 sg["opp_records"], sg["summary"], cop_commit),
                       results_dir / f"log_{game_id}_g{n:02d}.json")
    rows, final_result = score_series(played, opp, cop_commit, game_id)
    members = [m.strip() for m in args.members.split(",") if m.strip()]
    starts = [sg.get("started_at", "") for sg in played]
    ends = [sg.get("ended_at", "") for sg in played]
    write_artifact(build_declaration(game_id, game_uid, opp, members, cop_commit,
                                     starts[0] if starts else "", ends[-1] if ends else ""),
                   results_dir / f"declaration_{game_id}.json")
    result_obj = build_result(game_id, game_uid, opp, rows, final_result, cop_commit)
    write_artifact(result_obj, results_dir / f"result_{game_id}.json")
    print(f"[match] artifacts: {len(played)}x(config+log) + declaration + result "
          f"under results/ and config/games/")
    print(f"[match] result: {final_result['total_score']} winner={final_result['winner_group']}")
    if not args.no_email:
        try:
            token = REPO_ROOT / "secrets" / "gmail" / "token.json"
            mid = email_result(result_obj, args.report_to, f"result_{game_id}.json", token)
            print(f"[match] emailed result ONLY to {args.report_to} (id={mid})")
        except Exception as exc:
            print(f"[match] email FAILED ({type(exc).__name__}: {str(exc)[:140]})")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test", action="store_true", help="Play vs the local sparring peer")
    p.add_argument("--role", choices=["police", "thief"], default="police")
    p.add_argument("--sub-games", type=int, default=1)
    p.add_argument("--our-port", type=int, default=5011)
    p.add_argument("--sparring-port", type=int, default=8941)
    p.add_argument("--kit-root", type=Path, default=KIT_ROOT)
    # Real-match args:
    p.add_argument("--match", action="store_true", help="Play a live peer over reference-v3")
    p.add_argument("--opp-cop-url", help="Opponent cop MCP URL (dialed when we are thief)")
    p.add_argument("--opp-thief-url", help="Opponent thief MCP URL (dialed when we are cop)")
    p.add_argument("--opponent-group", default="anrbj666")
    p.add_argument("--our-cop-port", type=int, default=61224)
    p.add_argument("--our-thief-port", type=int, default=61223)
    p.add_argument("--setting", default="New York")
    # Result is emailed to OUR OWN inbox only (never the league address on friendlies).
    p.add_argument("--report-to", default="agentsorch@gmail.com")
    p.add_argument("--no-email", action="store_true", help="Skip emailing the result")
    p.add_argument("--members", default="", help="Comma-separated 'Name:id' for declaration")
    args = p.parse_args()

    if args.match:
        if not (args.opp_cop_url and args.opp_thief_url):
            print("ERROR: --match requires --opp-cop-url and --opp-thief-url")
            return 2
        result = asyncio.run(_play_match(
            opp_cop_url=args.opp_cop_url, opp_thief_url=args.opp_thief_url,
            our_cop_port=args.our_cop_port, our_thief_port=args.our_thief_port,
            opponent_group=args.opponent_group, setting=args.setting,
            sub_games=args.sub_games if args.sub_games > 1 else 6))
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
    result = asyncio.run(
        _self_test(args.role, args.sub_games, args.our_port, args.sparring_port, kit))
    print("\n[match] RESULT:", _json.dumps(result, indent=2))
    oks = [sg for sg in result["sub_games"] if sg.get("audit_ok")]
    sgs = result["sub_games"]
    rl_ok = all(sg["distinct_moves"] > 1 for sg in sgs) if sgs else False
    print(f"[match] STATUS: audits {len(oks)}/{len(result['sub_games'])} ok; "
          f"RL-varied-moves={rl_ok}")
    return 0 if oks and rl_ok else 1


if __name__ == "__main__":
    sys.exit(main())
