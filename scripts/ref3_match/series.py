"""The series loop: role alternation, index-hold convergence rule, settled-row discipline."""

from __future__ import annotations

import asyncio
import contextlib
import time

from ref3_match.net import NoGameHappenedError, _await_endpoint
from ref3_match.runtime_cfg import _t
from ref3_match.servers import _dial_and_play, _preflight_ports, _start_servers


def _error_row(sg: int, our_role: str, error: str) -> dict:
    return {"sub_game": sg, "role": our_role, "audit_ok": False, "error": error}


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
    from fastmcp import Client

    from cop_worker.protocol.reference_v3 import default_terms

    terms = default_terms({"setting": setting})
    _preflight_ports(our_cop_port, our_thief_port)
    sessions, tasks = await _start_servers("0.0.0.0", our_cop_port, our_thief_port)
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
            if hold_deadline is None:
                hold_deadline = time.monotonic() + _t("subgame_hold_sec", 300.0)
            # Wait ONLY for the endpoint this sub-game must dial (peer binds per-window).
            print(f"[match] sg{sg} ({our_role}) — awaiting peer endpoint {mcp_url}")
            if not await _await_endpoint(mcp_url, Client, window_s=_t("endpoint_await_sec", 900.0)):
                print(f"[match] sg{sg} peer window never opened — recording skip, continuing")
                results.append(_error_row(sg, our_role, "peer_window_never_opened"))
                sg += 1
                hold_deadline = None
                continue
            # Play once its window is open. A transient failure records the sub-game and
            # moves on — it never crashes the whole series (their windows re-run).
            try:
                sg_result = await _dial_and_play(
                    mcp_url,
                    base_url,
                    sessions[our_role],
                    sg=sg,
                    our_role=our_role,
                    terms=terms,
                    opponent_group=opponent_group,
                    members=members,
                    our_counted=our_counted,
                    scent_model=scent_model,
                    move_policy=move_policy,
                    confirmed_group=confirmed_group,
                )
                results.append(sg_result)
                # Learned from a VERIFIED handshake: declare the uid from sg2 onward.
                if sg_result.get("opponent_group"):
                    confirmed_group = sg_result["opponent_group"]
                print(f"[match] sg{sg} complete")
            except NoGameHappenedError as exc:
                # No game happened in this window (discovery / handshake / zero-turn
                # failure): HOLD the index and retry so a peer that holds-and-converges
                # can land on it, bounded by wall-clock — never by attempts. Only an
                # exhausted budget spends the number (files the row, moves on).
                if any(r.get("sub_game") == sg and r.get("audit_ok") for r in results):
                    # Settled rows are sacred: never replay a settled index.
                    print(f"[match] sg{sg} post-settlement noise — benign, continuing")
                elif time.monotonic() < hold_deadline:
                    print(
                        f"[match] sg{sg} no game happened "
                        f"({str(exc)[:110]}) — HOLDING index, retrying"
                    )
                    await asyncio.sleep(2.0)
                    continue
                else:
                    print(
                        f"[match] sg{sg} no game happened and hold budget exhausted "
                        f"({str(exc)[:90]}) — recording, continuing"
                    )
                    results.append(_error_row(sg, our_role, f"no_game_happened: {str(exc)[:180]}"))
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
                else:
                    print(
                        f"[match] sg{sg} failed "
                        f"({type(exc).__name__}: {str(exc)[:110]}) — continuing"
                    )
                    results.append(
                        _error_row(sg, our_role, f"{type(exc).__name__}: {str(exc)[:200]}")
                    )
            sg += 1
            hold_deadline = None
    finally:
        for t in tasks:
            t.cancel()
        for t in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
    return {"opponent": opponent_group, "sub_games": results}
