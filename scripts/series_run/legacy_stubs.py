"""Stubs for deleted modules (PeerRuntime, peer_result, mcp.coordinator).

These were removed in the Phase 1 restructure. The sentinel objects keep ruff
F821 clean on the unreachable legacy code paths retained in
``series_run.legacy_gamelets`` and ``series_run.legacy_exchange``.
"""


class _RemovedModule:
    """Placeholder for a module that was removed in Phase 1 restructure."""

    def __init__(self, *_a, **_kw) -> None:  # noqa: ANN001
        raise NotImplementedError("module removed in restructure")

    def __call__(self, *_a, **_kw):  # noqa: ANN001
        raise NotImplementedError("module removed in restructure")


PeerRuntime = _RemovedModule
ResultExchangeError = Exception  # satisfies except-clause; never raised by real code here


async def exchange_series_result(*_a, **_kw):  # noqa: ANN001
    """Stub — peer_result.exchange_series_result was removed in restructure."""
    raise NotImplementedError("peer_result removed in restructure")


def get_coordinator(*_a, **_kw):  # noqa: ANN001
    """Stub — mcp.coordinator.get_coordinator was removed in restructure."""
    raise NotImplementedError("mcp.coordinator removed in restructure")


def gamelet_from_game_id(*_a, **_kw):  # noqa: ANN001
    """Stub — mcp.coordinator.gamelet_from_game_id was removed in restructure."""
    raise NotImplementedError("mcp.coordinator removed in restructure")
