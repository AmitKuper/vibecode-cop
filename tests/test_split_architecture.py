"""Pins for the split architecture: worker stdio protocol, orchestrator series
semantics (index-hold, settled-row discipline), and the switching proxy.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from helpers_split_arch import _fake_launcher  # noqa: E402
from ref3_match.local_proxy import SwitchingProxy  # noqa: E402
from ref3_match.worker_proc import WorkerProc, WorkerProcError  # noqa: E402


def test_worker_proc_roundtrip(tmp_path):
    async def run():
        w = WorkerProc("police", {"port": 1}, launcher=_fake_launcher(tmp_path))
        await w.start()
        frame = await w.request({"type": "play", "sub_game": 3, "peer_url": "x"}, timeout_s=10)
        await w.stop()
        return frame

    frame = asyncio.run(run())
    assert frame == {"type": "result", "row": {"sub_game": 3}}


def test_worker_proc_reports_death_as_error(tmp_path):
    async def run():
        w = WorkerProc("thief", {"port": 1}, launcher=_fake_launcher(tmp_path))
        await w.start()
        w.proc.kill()
        await w.proc.wait()
        with pytest.raises(WorkerProcError):
            await w.request({"type": "play", "sub_game": 1, "peer_url": "x"}, timeout_s=5)
        await w.stop()

    asyncio.run(run())


def test_worker_fail_frames_reach_caller(tmp_path):
    async def run():
        init = {"port": 1, "reply": {"type": "fail", "kind": "no_game", "error": "no greeting"}}
        w = WorkerProc("police", init, launcher=_fake_launcher(tmp_path))
        await w.start()
        frame = await w.request({"type": "play", "sub_game": 1, "peer_url": "x"}, timeout_s=10)
        await w.stop()
        return frame

    frame = asyncio.run(run())
    assert frame["type"] == "fail" and frame["kind"] == "no_game"


def test_switching_proxy_routes_and_retargets():
    async def run():
        host = "127.0.0.1"
        payloads = {}

        async def backend(name, reader, writer):
            data = await reader.read(64)
            payloads.setdefault(name, []).append(data.decode())
            writer.write(f"{name}-ack".encode())
            await writer.drain()
            writer.close()

        async def echo_a(r, w):
            await backend("A", r, w)

        async def echo_b(r, w):
            await backend("B", r, w)

        sa = await asyncio.start_server(echo_a, host, 0)
        sb = await asyncio.start_server(echo_b, host, 0)
        pa = sa.sockets[0].getsockname()[1]
        pb = sb.sockets[0].getsockname()[1]
        proxy = SwitchingProxy(host, 0, pa)
        await proxy.start()
        listen = proxy._server.sockets[0].getsockname()[1]

        async def dial():
            reader, writer = await asyncio.open_connection(host, listen)
            writer.write(b"hello")
            await writer.drain()
            reply = await reader.read(64)
            writer.close()
            return reply.decode()

        first = await dial()
        await proxy.set_target(pb)
        second = await dial()
        await proxy.stop()
        sa.close()
        sb.close()
        return first, second

    first, second = asyncio.run(run())
    assert first == "A-ack" and second == "B-ack"


def test_series_split_import_and_error_row_shape():
    """The split loop reuses series.py's row vocabulary (settlement guard contract)."""
    from ref3_match.series import _error_row
    from ref3_match.series_split import _play_match_split, _settled

    row = _error_row(5, "thief", "worker: boom")
    assert row["sub_game"] == 5 and row["audit_ok"] is False
    assert _settled([{"sub_game": 5, "audit_ok": True}], 5)
    assert not _settled([row], 5)
    assert asyncio.iscoroutinefunction(_play_match_split)


def test_role_worker_protocol_is_json_lines():
    """The worker emits compact one-line JSON — the orchestrator reads line-wise."""
    from ref3_match import role_worker

    class Sink:
        def __init__(self):
            self.lines = []

        def write(self, s):
            self.lines.append(s)

        def flush(self):
            pass

    sink = Sink()
    role_worker._EMIT = sink
    role_worker._emit({"type": "ready", "role": "police"})
    assert sink.lines[0].endswith("\n") and "\n" not in sink.lines[0][:-1]
    assert json.loads(sink.lines[0]) == {"type": "ready", "role": "police"}
