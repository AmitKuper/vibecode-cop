"""Pin the orchestrator watchdog wiring: it heartbeats while alive, launches an
independent process, and stops cleanly (so it can never fire during teardown).
It must never touch gameplay state.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from ref3_match.watchdog_bridge import OrchestratorWatchdog  # noqa: E402


def test_watchdog_heartbeats_then_stops(monkeypatch):
    launched = {}

    def fake_launch(hb, ev, threshold_s=None):
        launched["hb"] = hb

        class _P:
            def terminate(self):
                launched["terminated"] = True

        return _P()

    import cop_worker.reliability.watchdog as wd_mod

    monkeypatch.setattr(wd_mod, "launch_watchdog_subprocess", fake_launch)
    # Beat fast so the test doesn't wait 5s.
    monkeypatch.setattr("ref3_match.watchdog_bridge.HEARTBEAT_INTERVAL_S", 0.02)

    async def run():
        wd = OrchestratorWatchdog("nis-yar1-vs-vibecode")
        await wd.start()
        await asyncio.sleep(0.1)  # let a few heartbeats land
        beats_after_start = json.loads(Path(launched["hb"]).read_text())["current_step"]
        await wd.stop()
        return beats_after_start

    beats = asyncio.run(run())
    assert beats >= 1  # heartbeat file was written while alive
    assert launched.get("terminated") is True  # watchdog process terminated on stop


def test_watchdog_start_survives_launch_failure(monkeypatch):
    import cop_worker.reliability.watchdog as wd_mod

    def boom(*a, **k):
        raise OSError("no subprocess")

    monkeypatch.setattr(wd_mod, "launch_watchdog_subprocess", boom)
    monkeypatch.setattr("ref3_match.watchdog_bridge.HEARTBEAT_INTERVAL_S", 0.02)

    async def run():
        wd = OrchestratorWatchdog("x")
        await wd.start()  # must not raise even if the process can't launch
        await asyncio.sleep(0.05)
        await wd.stop()

    asyncio.run(run())  # no exception = pass


def test_watchdog_tag_sanitizes_game_uid():
    wd = OrchestratorWatchdog("../evil/../id with spaces")
    name = Path(wd._hb).name  # only the filename must be sanitized (path has OS separators)
    assert "/" not in name and "\\" not in name and " " not in name
