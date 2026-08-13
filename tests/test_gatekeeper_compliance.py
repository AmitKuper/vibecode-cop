"""Pins for the signed rate_limiter_gatekeeper terms (Appendix E rules 28-29 +
Appendix F minimums): sustained 30/min pacing, 5s retry backoff, queue depth,
config-driven Gmail bucket, gatekeeper on the production email path, and the
inbound flood guard.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from cop_worker.gmail.gatekeeper import MIN_RETRY_DELAY_S, Gatekeeper
from cop_worker.gmail.token_bucket import load_gmail_rate
from cop_worker.net_gateway import (
    GatewayQueueFullError,
    NetGateway,
    load_queue_depth,
    load_rates,
)
from cop_worker.protocol.reference_v3.inbound_guard import InboundGuard


def test_signed_rates_thirty_per_minute_sustained():
    rates = load_rates()
    for kind in ("mcp", "http", "gmail"):
        capacity, refill = rates[kind]
        assert refill <= 0.5, f"{kind}: {refill}/s exceeds the signed 30/min sustained cap"
        assert capacity <= 30, f"{kind}: burst {capacity} exceeds the signed 30-request burst"


def test_retry_backoff_honors_signed_minimum():
    assert MIN_RETRY_DELAY_S >= 5.0


def test_gmail_bucket_is_config_driven():
    capacity, refill = load_gmail_rate()
    assert (capacity, refill) == (30.0, 0.5)


def test_queue_depth_loaded_and_enforced():
    assert load_queue_depth() == 100

    async def run():
        gw = NetGateway({"mcp": (1, 0.0001)}, queue_depth=1)

        async def slow():
            await asyncio.sleep(0.5)

        first = asyncio.ensure_future(gw.call("mcp", slow))
        await asyncio.sleep(0.05)  # first call now holds the single queue slot
        with pytest.raises(GatewayQueueFullError):
            await gw.call("mcp", slow)
        first.cancel()

    asyncio.run(run())


def test_gatekeeper_sends_to_explicit_recipient():
    sent = {}

    def sender(to, subject, body, attachments):
        sent["to"] = to
        return "msgid-1"

    gate = Gatekeeper(sender, capacity=30, refill_rate=1.0)
    gate.send("k1", "g1", "s", "{}", recipient="league@example.com")
    assert sent["to"] == "league@example.com"


def test_email_result_goes_through_gatekeeper(monkeypatch, tmp_path):
    from league_artifacts import report as report_mod

    calls = []
    monkeypatch.setattr(report_mod, "_GATEKEEPERS", {})
    monkeypatch.setattr(
        report_mod, "_mime_sender", lambda token: lambda to, s, b, a: calls.append(to) or "id-9"
    )
    result = {
        "game_id": "a-vs-b",
        "groups": ["a", "b"],
        "final_result": {"winner_group": "a", "total_score": {"a": 90, "b": 30}},
    }
    mid = report_mod.email_result(result, "x@example.com", "result_a-vs-b.json", tmp_path / "t")
    assert mid == "id-9" and calls == ["x@example.com"]
    # Same series re-filed: the gatekeeper's idempotency answers from cache, no second send.
    again = report_mod.email_result(result, "x@example.com", "result_a-vs-b.json", tmp_path / "t")
    assert again == "id-9" and calls == ["x@example.com"]


def test_inbound_guard_refuses_flood_only():
    guard = InboundGuard(max_per_minute=5)
    assert all(guard.allow() for _ in range(5))
    assert not guard.allow()
    assert guard.refused == 1
