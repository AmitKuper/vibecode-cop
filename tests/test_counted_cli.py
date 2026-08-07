from __future__ import annotations

import pytest

pytest.skip("module removed in restructure", allow_module_level=True)

"""Tests for counted CLI enforcement (Phase 1 v7)."""


import pytest

from cop_worker.runtime_mode import RuntimeMode

# ---------------------------------------------------------------------------
# 1. COUNTED mode requires exactly 6 gamelets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cli_mode_counted_requires_six_gamelets():
    """run_series with mode=COUNTED and n_gamelets!=6 must raise ValueError."""
    from pathlib import Path

    from scripts.run_series import run_series

    with pytest.raises(ValueError, match="6 gamelets"):
        await run_series(
            thief_url="http://localhost:5001/mcp",
            secret="real-prod-secret-xyz",
            config_sha256="deadbeef",
            games_dir=Path("/tmp/test_games"),
            n_gamelets=5,
            group_name="test-group",
            mode=RuntimeMode.COUNTED,
        )


# ---------------------------------------------------------------------------
# 2. DEVELOPMENT mode accepts other gamelet counts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cli_mode_development_allows_other_counts(tmp_path, monkeypatch):
    """run_series with mode=DEVELOPMENT and n_gamelets=3 should not raise ValueError."""
    from scripts.run_series import run_series

    # Patch out the PeerRuntime so no network calls happen
    async def _fake_run_game(game_id, **kwargs):
        return {"winner": "cop", "audit_ok": True, "final_step": 5}

    import unittest.mock as mock

    with mock.patch("agent.peer_runtime.PeerRuntime") as mock_runtime_cls:
        instance = mock_runtime_cls.return_value
        instance.run_game = _fake_run_game

        # Should NOT raise ValueError for n_gamelets=3 in DEVELOPMENT mode
        # (May fail on PeerRuntime init — that's fine, we just verify no ValueError for gamelets)
        try:
            await run_series(
                thief_url="http://localhost:5001/mcp",
                secret="dev-secret",
                config_sha256="deadbeef",
                games_dir=tmp_path,
                n_gamelets=3,
                group_name="test-group",
                mode=RuntimeMode.DEVELOPMENT,
            )
        except ValueError as exc:
            # Must NOT be the "6 gamelets" error
            assert "6 gamelets" not in str(exc), f"Unexpected 6-gamelet error: {exc}"
        except Exception:
            pass  # Network errors etc. are expected in tests


# ---------------------------------------------------------------------------
# 3. PeerRuntime receives counted_mode=True when mode=COUNTED
# ---------------------------------------------------------------------------


def test_runtime_mode_propagated_to_peer_runtime():
    """PeerRuntime should expose counted_mode=True when constructed for COUNTED mode."""
    from unittest.mock import patch

    from cop_worker.peer_runtime import PeerRuntime

    # Patch external deps so PeerRuntime can be instantiated
    with (
        patch("agent.peer_runtime_io._load_start_positions", return_value=((0, 0), (6, 6))),
        patch("agent.peer_runtime.PeerRuntime._init_llm", return_value=None),
    ):
        runtime = PeerRuntime(
            role="cop",
            secret="test-secret",
            config_sha256="deadbeef",
            opponent_url="http://localhost:5001/mcp",
            counted_mode=True,
        )
        assert runtime.counted_mode is True
