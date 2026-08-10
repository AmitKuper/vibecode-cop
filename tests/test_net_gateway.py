"""The outbound gateway: pacing, bounded retries, and hard-failure semantics."""

from __future__ import annotations

import pytest

from cop_worker.net_gateway import GATEWAY, NetGateway


class TestNetGateway:
    async def test_success_passes_the_return_value_through(self) -> None:
        gw = NetGateway({"mcp": (5, 100.0)})

        async def ok():
            return {"ok": True}

        assert await gw.call("mcp", ok) == {"ok": True}

    async def test_retries_then_succeeds(self) -> None:
        gw = NetGateway({"mcp": (5, 100.0)})
        attempts = []

        async def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise TimeoutError("transient")
            return "settled"

        result = await gw.call("mcp", flaky, retries=4, backoff_s=0.01)
        assert result == "settled" and len(attempts) == 3

    async def test_exhausted_retries_reraise_the_last_error(self) -> None:
        gw = NetGateway({"mcp": (5, 100.0)})

        async def always_down():
            raise ConnectionError("edge gone")

        with pytest.raises(ConnectionError):
            await gw.call("mcp", always_down, retries=2, backoff_s=0.01)

    async def test_unknown_kind_refuses_loudly(self) -> None:
        gw = NetGateway({"mcp": (5, 100.0)})

        async def noop():
            return None

        with pytest.raises(KeyError, match="unknown gateway kind"):
            await gw.call("smtp", noop)

    async def test_bucket_paces_burst_beyond_capacity(self) -> None:
        import time

        gw = NetGateway({"mcp": (2, 50.0)})  # capacity 2, fast refill so the test is quick

        async def ok():
            return 1

        start = time.monotonic()
        for _ in range(4):
            await gw.call("mcp", ok)
        # 2 burst + 2 refilled at 50/s → at least ~0.02s of pacing occurred.
        assert time.monotonic() - start >= 0.02

    async def test_process_wide_instance_has_the_wire_kinds(self) -> None:
        async def ok():
            return "x"

        assert await GATEWAY.call("mcp", ok) == "x"
        assert await GATEWAY.call("llm", ok) == "x"
