from __future__ import annotations

import pytest

pytest.skip("module removed in restructure", allow_module_level=True)

"""Phase 2 v8 remediation tests — local truth / information-hiding verification."""


# ---------------------------------------------------------------------------
# Recursive leak checker
# ---------------------------------------------------------------------------


def _find_keys_recursive(d, forbidden_keys, path=""):
    """Return list of paths for any forbidden key found recursively in nested dicts/lists."""
    found = []
    if isinstance(d, dict):
        for k, v in d.items():
            if k in forbidden_keys:
                found.append(f"{path}.{k}" if path else k)
            found.extend(_find_keys_recursive(v, forbidden_keys, path=f"{path}.{k}" if path else k))
    elif isinstance(d, (list, tuple)):
        for i, item in enumerate(d):
            found.extend(_find_keys_recursive(item, forbidden_keys, path=f"{path}[{i}]"))
    return found


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_board(grid_size=7):
    from cop_worker.board import Board

    return Board(
        cop_position=[0, 0],
        thief_position=[3, 3],
        grid_size=grid_size,
    )


def _one_hot_grid(n, x, y):
    grid = [[0.0] * n for _ in range(n)]
    grid[y][x] = 1.0
    return grid


# ---------------------------------------------------------------------------
# Test 1: thief_observation channel 1 is NOT the exact cop one-hot
# ---------------------------------------------------------------------------


def test_thief_observation_channel1_is_not_cop_one_hot():
    """Channel 1 must be scent field, not the live cop position 1-hot."""
    from cop_worker.rl.observation import thief_observation

    board = _make_board()
    n = board.grid_size
    cx, cy = board.cop_position  # [0, 0]

    # Call with no scent (all zeros)
    obs = thief_observation(board, max_steps=35, cop_scent_field=None)
    assert len(obs) == 4, "thief obs must have 4 channels"

    ch1 = obs[1]
    cop_one_hot = _one_hot_grid(n, cx, cy)

    # Channel 1 (zeros when no scent) must NOT equal the cop one-hot (which has a 1 at [0][0])
    assert ch1 != cop_one_hot, (
        "Channel 1 must not be the cop position one-hot; "
        "it should be the scent field (zeros when no scent provided)"
    )

    # Extra: if cop is at [0,0], the cop one-hot has grid[0][0]=1.0; scent should be 0.0 there
    assert ch1[cy][cx] == 0.0, "With no scent provided, channel 1 should be all zeros"


# ---------------------------------------------------------------------------
# Test 2: build_local_observation does not contain forbidden keys
# ---------------------------------------------------------------------------


def test_build_local_observation_no_hidden_coords():
    """build_local_observation must not expose cop_position, thief_position, opponent_position."""
    from cop_worker.peer_turn_helpers import build_local_observation

    obs = build_local_observation(
        role="thief",
        own_position=(3, 3),
        barriers=[],
        opponent_scent=[],
        last_hint="",
        step=1,
        gamelet=1,
        grid_size=7,
        own_barriers_remaining=14,
        belief_engine=None,
    )

    forbidden = {"cop_position", "thief_position", "opponent_position"}
    leaks = _find_keys_recursive(obs, forbidden)
    assert not leaks, f"build_local_observation leaks hidden coords: {leaks}"


# ---------------------------------------------------------------------------
# Test 3: build_board_state IS allowed to have both positions (private commitment)
# ---------------------------------------------------------------------------


def test_build_board_state_has_both_positions():
    """build_board_state is the private commitment dict — it must contain both positions."""
    from cop_worker.peer_turn_helpers import build_board_state

    from cop_worker.board import Board

    class _FakeRuntime:
        role = "cop"
        game_id = ""
        config_sha256 = "abc"
        _cop_barriers_remaining = 14
        board = Board(cop_position=[0, 0], thief_position=[3, 3])

    bs = build_board_state(_FakeRuntime())
    assert "cop_position" in bs, "build_board_state must include cop_position (private commitment)"
    assert "thief_position" in bs, "build_board_state must include thief_position"


# ---------------------------------------------------------------------------
# Test 4: _CrewMixin fallback _build_observation does not include grid_state
# ---------------------------------------------------------------------------


def test_crew_mixin_build_observation_no_grid_state():
    """_CrewMixin fallback _build_observation must not expose grid_state key."""
    # Import PeerRuntime which inherits _CrewMixin (or its fallback)
    from cop_worker.peer_runtime import PeerRuntime

    # Build a minimal fake instance (without calling __init__)
    runtime = object.__new__(PeerRuntime)
    runtime.role = "cop"

    gs = {
        "cop_position": [0, 0],
        "thief_position": [3, 3],
        "turn": 1,
        "scent_field": [],
    }
    obs = runtime._build_observation(gs)
    assert "grid_state" not in obs, (
        "_build_observation must not include 'grid_state' key (leaks both positions)"
    )


# ---------------------------------------------------------------------------
# Test 5: local_obs_to_tensor shape — thief obs has 4 channels, no hidden coord
# ---------------------------------------------------------------------------


def test_thief_observation_shape():
    """thief_observation must return exactly 4 channels of shape (grid_size, grid_size)."""
    from cop_worker.rl.observation import observation_shape, thief_observation

    n = 7
    board = _make_board(n)
    obs = thief_observation(board, max_steps=35, cop_scent_field=None)

    assert len(obs) == 4, f"Expected 4 channels, got {len(obs)}"
    for i, ch in enumerate(obs):
        assert len(ch) == n, f"Channel {i} height mismatch: {len(ch)} != {n}"
        assert len(ch[0]) == n, f"Channel {i} width mismatch: {len(ch[0])} != {n}"

    shape = observation_shape(n, role="thief")
    assert shape == (4, n, n), f"observation_shape mismatch: {shape}"


# ---------------------------------------------------------------------------
# Test 6: build_public_transition_root returns 64-char hex
# ---------------------------------------------------------------------------


def test_build_public_transition_root_hex():
    """build_public_transition_root must return a 64-char lowercase hex string."""
    from cop_worker.crypto import build_public_transition_root

    result = build_public_transition_root(
        game_uid="game-123",
        gamelet=1,
        step=5,
        declaration_hash="abc",
        config_hash="def",
        protocol_hash="ghi",
        public_barriers=[[1, 2], [3, 4]],
        cop_barriers_quota=14,
        revealed_cop_move="NORTH",
        revealed_thief_move="SOUTH",
        previous_transcript_root="",
        public_outcome="",
    )
    assert isinstance(result, str), "Must return a string"
    assert len(result) == 64, f"SHA-256 hex must be 64 chars, got {len(result)}"
    assert result == result.lower(), "Must be lowercase hex"
    # Basic hex check
    int(result, 16)


# ---------------------------------------------------------------------------
# Test 7: build_private_state_commitment non-enumerable properties
# ---------------------------------------------------------------------------


def test_build_private_state_commitment_non_enumerable():
    """Different positions → different hashes; different nonces → different hashes."""
    from cop_worker.crypto import build_private_state_commitment

    base_kwargs = {
        "own_barriers_remaining": 14,
        "step": 1,
        "gamelet": 1,
        "game_uid": "game-123",
    }

    nonce = "a" * 64  # fixed nonce

    h1 = build_private_state_commitment(own_position=(0, 0), local_nonce=nonce, **base_kwargs)
    h2 = build_private_state_commitment(own_position=(1, 1), local_nonce=nonce, **base_kwargs)
    assert h1 != h2, "Different positions with same nonce must produce different hashes"

    nonce2 = "b" * 64
    h3 = build_private_state_commitment(own_position=(0, 0), local_nonce=nonce, **base_kwargs)
    h4 = build_private_state_commitment(own_position=(0, 0), local_nonce=nonce2, **base_kwargs)
    assert h3 != h4, "Same position with different nonces must produce different hashes"

    # Verify hex length
    assert len(h1) == 64


# ---------------------------------------------------------------------------
# Test 8: Recursive dict leak checker detects nested cop_position
# ---------------------------------------------------------------------------


def test_recursive_leak_checker_finds_nested_keys():
    """_find_keys_recursive must detect forbidden keys at any nesting depth."""
    forbidden = {"cop_position", "thief_position", "opponent_position"}

    # Should find nested key
    nested = {"outer": {"inner": {"cop_position": [0, 0]}}}
    leaks = _find_keys_recursive(nested, forbidden)
    assert leaks, "Must detect cop_position nested inside dicts"
    assert any("cop_position" in p for p in leaks)

    # Should find key in list element
    in_list = {"obs": [{"thief_position": [3, 3]}, "other"]}
    leaks2 = _find_keys_recursive(in_list, forbidden)
    assert leaks2, "Must detect thief_position nested inside a list"

    # Clean dict should return empty
    clean = {"own_position": [0, 0], "scent_field": [], "turn": 1}
    assert _find_keys_recursive(clean, forbidden) == [], "Clean dict should have no leaks"

    # Verify thief_observation output (with no scent) is also clean
    from cop_worker.rl.observation import thief_observation

    board = _make_board()
    obs = thief_observation(board, max_steps=35, cop_scent_field=None)
    # obs is a list of channel grids — no dict keys, so leak checker should find nothing
    leaks3 = _find_keys_recursive({"channels": obs}, forbidden)
    assert not leaks3, f"thief_observation output leaks hidden coords: {leaks3}"
