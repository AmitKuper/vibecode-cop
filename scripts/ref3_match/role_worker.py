"""Role-worker process: ONE role's endpoint and ONLY that role's windows.

The rule-1 building block: the orchestrator spawns one of these for the cop and
one for the thief, so police code and thief code run in two completely separate
OS processes and share no memory. Wire protocol to the orchestrator is JSON
lines: stdin carries {init}, then {"type":"play",...} / {"type":"shutdown"};
stdout carries {"type":"ready"|"result"|"fail",...}. Everything the play path
prints is redirected to stderr, which the orchestrator pumps into its own log.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys

from ref3_match.worker_strays import _drain_strays  # noqa: E402

_EMIT = None  # the real stdout handle, reserved for protocol frames only


def _emit(obj: dict) -> None:
    _EMIT.write(json.dumps(obj, separators=(",", ":")) + "\n")
    _EMIT.flush()


async def _read_line() -> str:
    """Blocking stdin readline in a thread (Windows-safe: no connect_read_pipe)."""
    return await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)


async def _play_window(cmd: dict, session, init: dict) -> dict:
    from fastmcp import Client

    from ref3_match import settled_row
    from ref3_match.net import NoGameHappenedError, _await_endpoint
    from ref3_match.runtime_cfg import _t
    from ref3_match.servers import _dial_and_play

    peer_url = cmd["peer_url"]
    mcp_url = peer_url if peer_url.endswith("/mcp") else peer_url.rstrip("/") + "/mcp"
    base_url = mcp_url.removesuffix("/mcp")
    sg = int(cmd["sub_game"])
    session.agreements.extend(cmd.get("inject_greetings") or [])
    if not await _await_endpoint(
        mcp_url, Client, window_s=float(cmd.get("await_s") or _t("endpoint_await_sec", 900.0))
    ):
        return {"type": "fail", "kind": "window_never_opened", "sub_game": sg}
    try:
        row = await _dial_and_play(
            mcp_url,
            base_url,
            session,
            sg=sg,
            our_role=init["role"],
            terms=init["terms"],
            opponent_group=init["opponent_group"],
            members=init.get("members"),
            our_counted=int(init.get("our_counted", 0)),
            scent_model=init["scent_model"],
            move_policy=init["move_policy"],
            confirmed_group=cmd.get("confirmed_group"),
            series_label=init.get("series_label", ""),
        )
        return {
            "type": "result",
            "sub_game": sg,
            "row": row,
            "stray_greetings": _drain_strays(session, beyond=sg),
        }
    except NoGameHappenedError as exc:
        return {"type": "fail", "kind": "no_game", "sub_game": sg, "error": str(exc)[:200]}
    except Exception as exc:  # any other failure
        detail = f"{type(exc).__name__}: {str(exc)[:200]}"
        settled = settled_row.recover(session, sg)
        if settled is not None:  # audit already verified - see ref3_match.settled_row
            settled["post_settlement_error"] = detail
            print(f"[match] sg{sg} settled, then {detail} — reporting the settlement")
            return {"type": "result", "sub_game": sg, "row": settled, "stray_greetings": []}
        return {"type": "fail", "kind": "error", "sub_game": sg, "error": detail}


async def _main() -> int:
    global _EMIT
    _EMIT = sys.stdout
    sys.stdout = sys.stderr  # play-path prints become worker logs, never protocol frames

    init = json.loads(await _read_line())
    from ref3_match.door_guard import ensure_door_answers
    from ref3_match.gui_bridge import maybe_start_gui, stop_gui
    from ref3_match.runtime_cfg import apply_runtime_config
    from ref3_match.servers import _start_server_one
    from ref3_match.worker_log import install_worker_log

    log_path = install_worker_log(init["role"])  # survives a dead stderr pump

    apply_runtime_config(init.get("runtime") or {})
    role = init["role"]
    session, server_task = await _start_server_one(
        init.get("host", "0.0.0.0"), int(init["port"]), role
    )
    gui_task = await maybe_start_gui(role, init)  # None unless init carries "gui_port"
    print(
        f"[{role}-worker] endpoint live on :{init['port']} "
        f"(pid={__import__('os').getpid()}, log={log_path})"
    )
    _emit({"type": "ready", "role": role})

    try:
        while True:
            line = await _read_line()
            if not line:  # orchestrator died / closed stdin: exit rather than linger
                return 0
            cmd = json.loads(line)
            if cmd.get("type") == "shutdown":
                _emit({"type": "bye"})
                return 0
            if cmd.get("type") == "play":
                # Self-heal a wedged inbound door before playing (same session,
                # fresh HTTP stack — banked greetings survive). See door_guard.
                session, server_task = await ensure_door_answers(role, init, session, server_task)
                _emit(await _play_window(cmd, session, init))
            elif cmd.get("type") == "drain":
                _emit({"type": "strays", "stray_greetings": _drain_strays(session)})
            else:
                _emit({"type": "fail", "kind": "bad_command", "error": str(cmd)[:100]})
    finally:
        stop_gui(gui_task)
        server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await server_task


def main() -> int:
    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())
