"""Self-test on the SPLIT architecture: two role workers vs the kit sparring peer.

Same two-group game as selftest.py (our production stack vs the kit's
independent implementation), but with cop and thief in separate OS processes.
The sparring peer only dials one --peer URL, so a SwitchingProxy presents a
single stable port and forwards each window to the active role worker.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

from ref3_match.local_proxy import SwitchingProxy
from ref3_match.net import _wait_port
from ref3_match.runtime_cfg import runtime_snapshot
from ref3_match.series import _error_row
from ref3_match.watchdog_bridge import OrchestratorWatchdog
from ref3_match.worker_proc import WorkerProc, WorkerProcError, absorb_strays, drain_other


async def _self_test_split(
    role: str,
    sub_games: int,
    our_port: int,
    sparring_port: int,
    kit: Path,
    scent_model: str = "multiplicative_book_v1",
    move_policy: str = "rl",
) -> dict:
    from cop_worker.protocol.reference_v3 import default_terms

    host = "127.0.0.1"
    cop_port, thief_port = our_port + 11, our_port + 12
    sparring_url = f"http://{host}:{sparring_port}"
    sparring_role = "police" if role == "thief" else "thief"
    terms = default_terms({"setting": "Haifa"})

    # Local harness: short greeting-poll so a misrouted Step-0 fails fast and the
    # drain-and-retry loop converges well inside the hold budget.
    runtime = runtime_snapshot()
    runtime.setdefault("timeouts", {}).setdefault("agreement_poll_sec", 45.0)
    base_init = {
        "host": host,
        "terms": terms,
        "runtime": runtime,
        "opponent_group": "sparring-match",
        "members": [],
        "our_counted": 0,
        "scent_model": scent_model,
        "move_policy": move_policy,
    }
    workers = {
        "police": WorkerProc("police", dict(base_init, port=cop_port)),
        "thief": WorkerProc("thief", dict(base_init, port=thief_port)),
    }
    ports = {"police": cop_port, "thief": thief_port}
    await asyncio.gather(*(w.start() for w in workers.values()))
    watchdog = OrchestratorWatchdog("selftest")  # exercise the rule-7 watchdog here too
    await watchdog.start()

    proxy = SwitchingProxy(host, our_port, ports[role])
    await proxy.start()
    print(f"[match] SPLIT self-test: proxy :{our_port} → cop :{cop_port} / thief :{thief_port}")

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
            f"http://{host}:{our_port}/mcp",
            "--group-id",
            "sparring-match",
            "--await-peer",
        ],
        cwd=kit,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    results: list[dict] = []
    other = {"police": "thief", "thief": "police"}
    pending: dict[int, list] = {}  # misrouted greetings, banked per sub-game
    try:
        await _wait_port(host, sparring_port, timeout=30.0)
        await asyncio.sleep(2.0)
        for sg in range(1, sub_games + 1):
            sg_role = role if sg % 2 == 1 else other[role]
            deadline = asyncio.get_event_loop().time() + 120.0  # local hold budget
            while True:
                # The single-URL peer may have delivered this window's greeting to
                # the previously targeted worker — pull it over, then retarget.
                await drain_other(workers[other[sg_role]], pending)
                await proxy.set_target(ports[sg_role])
                try:
                    frame = await workers[sg_role].request(
                        {
                            "type": "play",
                            "sub_game": sg,
                            "peer_url": sparring_url,
                            "confirmed_group": None,
                            "await_s": 60.0,
                            "inject_greetings": pending.pop(sg, []),
                        },
                        timeout_s=480.0,
                    )
                except WorkerProcError as exc:
                    results.append(_error_row(sg, sg_role, f"worker: {str(exc)[:180]}"))
                    await workers[sg_role].restart()
                    break
                absorb_strays(pending, frame)
                if (
                    frame.get("type") == "fail"
                    and frame.get("kind") == "no_game"
                    and asyncio.get_event_loop().time() < deadline
                ):
                    print(f"[match] sg{sg} no game happened — re-draining and retrying")
                    continue
                if frame.get("type") == "result":
                    results.append(frame["row"])
                else:
                    results.append(_error_row(sg, sg_role, str(frame.get("error"))[:200]))
                break
    finally:
        await watchdog.stop()
        await proxy.stop()
        await asyncio.gather(*(w.stop() for w in workers.values()), return_exceptions=True)
        sparring.terminate()
        try:
            sparring.wait(timeout=8)
        except Exception:
            sparring.kill()
    return {"role": role, "sub_games": results}
