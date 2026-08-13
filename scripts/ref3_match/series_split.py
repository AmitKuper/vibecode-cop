"""The series loop on the SPLIT architecture: three processes, same semantics.

Spawns one cop worker and one thief worker (Appendix E rules 1-3) and preserves
series.py's conventions: role alternation, index-hold convergence, settled-row
discipline, teardown-noise absorption. Holds no game secrets — nonces, commits
and movers live inside the role workers.
"""

from __future__ import annotations

import asyncio
import time

from ref3_match.net import _check_port
from ref3_match.runtime_cfg import _t, runtime_snapshot
from ref3_match.series import _error_row
from ref3_match.watchdog_bridge import OrchestratorWatchdog
from ref3_match.worker_proc import WorkerProc, WorkerProcError, absorb_strays, drain_other


def _settled(results: list, sg: int) -> bool:
    return any(r.get("sub_game") == sg and r.get("audit_ok") for r in results)


async def _play_match_split(
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
    """Real match over reference-v3 with one OS process per role + this orchestrator."""
    from cop_worker.protocol.reference_v3 import default_terms

    for pname, port in (("cop", our_cop_port), ("thief", our_thief_port)):
        if _check_port("127.0.0.1", port):
            raise RuntimeError(f"port {port} (our {pname} endpoint) is already in use")

    terms = default_terms({"setting": setting})
    base_init = {
        "host": "0.0.0.0",
        "terms": terms,
        "runtime": runtime_snapshot(),
        "opponent_group": opponent_group,
        "members": members or [],
        "our_counted": our_counted,
        "scent_model": scent_model,
        "move_policy": move_policy,
    }
    from ref3_match.worker_proc import role_init

    net = runtime_snapshot().get("network", {})
    workers = {
        "police": WorkerProc("police", role_init(base_init, our_cop_port, net.get("gui_cop_port"))),
        "thief": WorkerProc(
            "thief", role_init(base_init, our_thief_port, net.get("gui_thief_port"))
        ),
    }
    await asyncio.gather(*(w.start() for w in workers.values()))
    watchdog = OrchestratorWatchdog(opponent_group)  # independent watchdog on us (rule 7)
    await watchdog.start()
    print(
        f"[match] SPLIT arch: cop pid={workers['police'].proc.pid} "
        f"thief pid={workers['thief'].proc.pid} orchestrator holds no game state"
    )

    results: list[dict] = []
    pending: dict[int, list] = {}  # greetings a single-URL peer delivered to the wrong role
    confirmed_group: str | None = (
        opponent_group if opponent_group and not opponent_group.startswith("sparring") else None
    )
    await_s = float(_t("endpoint_await_sec", 900.0))
    reply_cap = await_s + float(_t("subgame_play_sec", 600.0)) + 60.0
    try:
        sg = 1
        hold_deadline: float | None = None
        while sg <= sub_games:
            our_role = "thief" if sg % 2 == 1 else "police"
            peer_url = opp_cop_url if our_role == "thief" else opp_thief_url
            if hold_deadline is None:
                hold_deadline = time.monotonic() + _t("subgame_hold_sec", 300.0)
            print(f"[match] sg{sg} ({our_role}) — dispatching to {our_role} worker")
            await drain_other(workers["thief" if our_role == "police" else "police"], pending)
            try:
                frame = await workers[our_role].request(
                    {
                        "type": "play",
                        "sub_game": sg,
                        "peer_url": peer_url,
                        "confirmed_group": confirmed_group,
                        "await_s": await_s,
                        "inject_greetings": pending.pop(sg, []),
                    },
                    timeout_s=reply_cap,
                )
            except WorkerProcError as exc:
                if _settled(results, sg):
                    print(f"[match] sg{sg} worker noise after settlement — benign, continuing")
                else:
                    print(f"[match] sg{sg} worker failed ({str(exc)[:110]}) — filing, continuing")
                    results.append(_error_row(sg, our_role, f"worker: {str(exc)[:180]}"))
                await workers[our_role].restart()
                sg += 1
                hold_deadline = None
                continue

            absorb_strays(pending, frame)
            kind = frame.get("type")
            if kind == "result":
                results.append(frame["row"])
                if frame["row"].get("opponent_group"):
                    confirmed_group = frame["row"]["opponent_group"]
                print(f"[match] sg{sg} complete")
            elif kind == "fail" and frame.get("kind") == "no_game":
                if _settled(results, sg):
                    print(f"[match] sg{sg} post-settlement noise — benign, continuing")
                elif time.monotonic() < hold_deadline:
                    print(
                        f"[match] sg{sg} no game happened "
                        f"({str(frame.get('error'))[:110]}) — HOLDING index, retrying"
                    )
                    await asyncio.sleep(2.0)
                    continue
                else:
                    print(f"[match] sg{sg} hold budget exhausted — recording, continuing")
                    results.append(
                        _error_row(sg, our_role, f"no_game_happened: {frame.get('error')}")
                    )
            elif kind == "fail" and frame.get("kind") == "window_never_opened":
                print(f"[match] sg{sg} peer window never opened — recording skip, continuing")
                results.append(_error_row(sg, our_role, "peer_window_never_opened"))
            else:  # generic error frame
                if _settled(results, sg):
                    print(f"[match] sg{sg} teardown noise after settlement — benign, continuing")
                else:
                    print(f"[match] sg{sg} failed ({str(frame.get('error'))[:110]}) — continuing")
                    results.append(_error_row(sg, our_role, str(frame.get("error"))[:200]))
            sg += 1
            hold_deadline = None
    finally:
        await watchdog.stop()  # first: the watchdog must not fire during teardown
        await asyncio.gather(*(w.stop() for w in workers.values()), return_exceptions=True)
    return {"opponent": opponent_group, "sub_games": results}
