"""Tests for deterministic fixture opponents (Phase 10D)."""

import hashlib
import json

import pytest

from cop_worker.mcp.fixture_protocols import FixtureOpponent, IncompatibleFixture


@pytest.mark.asyncio
async def test_fixture_handles_start_game():
    fixture = FixtureOpponent(role="thief")
    result = await fixture.handle("start_game", {})
    assert result["status"] == "ok"
    assert result["role"] == "thief"
    assert result["ready"] is True


@pytest.mark.asyncio
async def test_fixture_handles_commit_returns_h_commit():
    fixture = FixtureOpponent(role="cop")
    result = await fixture.handle("action", {"phase": "commit"})
    assert result["status"] == "ok"
    assert "h_commit" in result
    assert len(result["h_commit"]) == 64  # sha256 hex


@pytest.mark.asyncio
async def test_fixture_handles_reveal_matches_commit():
    fixture = FixtureOpponent(role="cop")
    commit_result = await fixture.handle("action", {"phase": "commit"})
    step = commit_result["step"]
    reveal_result = await fixture.handle("action", {"phase": "reveal", "step": step})
    assert reveal_result["status"] == "ok"
    assert "move" in reveal_result
    assert "nonce" in reveal_result


@pytest.mark.asyncio
async def test_fixture_commit_reveal_verifies():
    """Build h_commit from reveal fields and verify it matches the commit."""
    fixture = FixtureOpponent(role="thief")
    commit_result = await fixture.handle("action", {"phase": "commit"})
    h_commit = commit_result["h_commit"]
    step = commit_result["step"]

    reveal_result = await fixture.handle("action", {"phase": "reveal", "step": step})
    move = reveal_result["move"]
    nonce = reveal_result["nonce"]

    # Recompute h_commit from revealed data
    payload = json.dumps({"move": move, "nonce": nonce}, sort_keys=True, separators=(",", ":"))
    expected_h_commit = hashlib.sha256(payload.encode()).hexdigest()
    assert h_commit == expected_h_commit


@pytest.mark.asyncio
async def test_incompatible_fixture_different_semantics():
    fixture = IncompatibleFixture()
    result = await fixture.handle("start_game", {})
    assert result.get("commitment_semantics") == "move_only"
    # This is the signal that capability negotiation must reject this peer
