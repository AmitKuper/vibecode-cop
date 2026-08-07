"""Compliance tests verifying mandatory project rules from skill definitions."""

from pathlib import Path

import pytest

from agent.board import Board
from agent.orchestrator import GameOrchestrator
from agent.rules_engine import RulesEngine

# ---------------------------------------------------------------------------
# Hidden-information: no opponent_position in observations
# ---------------------------------------------------------------------------


def _make_rules() -> tuple[Board, RulesEngine]:
    board = Board(cop_position=[0, 0], thief_position=[3, 3])
    return board, RulesEngine(board)


def test_orchestrator_observation_has_no_opponent_position():
    """Cop and thief observations must NOT expose opponent raw coordinates."""
    orch = GameOrchestrator.__new__(GameOrchestrator)
    orch.role = "cop"
    game_state = {
        "cop_position": [1, 2],
        "thief_position": [4, 5],
        "turn": 3,
        "scent_field": [],
    }
    obs = orch._build_observation(game_state)
    assert "opponent_position" not in obs, "opponent_position must not appear in cop observation"
    assert "scent_field" in obs, "scent_field must be present in observation"


def test_orchestrator_observation_thief_has_no_opponent_position():
    orch = GameOrchestrator.__new__(GameOrchestrator)
    orch.role = "thief"
    game_state = {
        "cop_position": [1, 2],
        "thief_position": [4, 5],
        "turn": 3,
        "scent_field": [],
    }
    obs = orch._build_observation(game_state)
    assert "opponent_position" not in obs, "opponent_position must not appear in thief observation"


# ---------------------------------------------------------------------------
# Scent: accumulated and decaying over turns
# ---------------------------------------------------------------------------


def test_scent_accumulates_after_moves():
    """Scent must persist across turns, not reset to zero each call."""
    board, rules = _make_rules()
    # Initial scent grid is all zeros
    initial = rules.get_scent_field()
    assert all(v == 0.0 for row in initial for v in row), "Scent must start at zero"

    # Apply one move: thief moves SOUTH, scent emitted at new position
    rules.apply_moves("STAY", "SOUTH")
    after_one = rules.get_scent_field()
    tx, ty = board.thief_position
    # Center of scent field should be at thief's new position
    assert after_one[ty][tx] == pytest.approx(0.9, abs=0.01), (
        "Scent center must equal SCENT_CENTER at thief's position"
    )


def test_scent_decays_when_thief_moves_away():
    """Old scent cells must decay once the thief has moved away."""
    board, rules = _make_rules()
    # Thief at [3,3]: emit scent there
    rules.apply_moves("STAY", "STAY")
    old_tx, old_ty = 3, 3
    scent_at_old = rules.get_scent_field()[old_ty][old_tx]
    assert scent_at_old == pytest.approx(0.9, abs=0.01)

    # Thief moves NORTH to [3,2]; old position [3,3] is now at distance 1 from new position.
    # Additive update: 0.9 * 0.9 + 0.62 = 1.43 (kernel[dist_sq=1] = 0.62)
    rules.apply_moves("STAY", "NORTH")
    scent_after = rules.get_scent_field()[old_ty][old_tx]
    assert scent_after == pytest.approx(0.9 * 0.9 + 0.62, abs=0.01), (
        "Scent must follow additive model: 0.9 * old + emission"
    )
    assert scent_after < 1.5, "Scent value must remain bounded"


def test_fresh_snapshot_unchanged_for_rl():
    """compute_scent_field() must still return a fresh snapshot (RL backward compat)."""
    board, rules = _make_rules()
    tx, ty = board.thief_position
    snap = rules.compute_scent_field()
    assert snap[ty][tx] == pytest.approx(0.9, abs=0.01), (
        "Fresh snapshot must peak at current thief position"
    )
    # Confirm it does NOT use accumulated history by checking before any apply_moves
    accum = rules.get_scent_field()
    assert accum[ty][tx] == 0.0, "Accumulated scent must be zero before any moves"


# ---------------------------------------------------------------------------
# Config: max_turns from constructor, minimum enforced
# ---------------------------------------------------------------------------


def test_rules_engine_respects_max_turns_param():
    """When max_turns > 35 is negotiated, game should not end at 35."""
    board = Board(cop_position=[0, 0], thief_position=[6, 6])
    rules = RulesEngine(board, max_turns=50)
    assert rules.max_turns == 50
    board.turn = 35  # Should still be ONGOING since max_turns=50
    from agent.rules_engine import GameOutcome

    assert rules.check_game_status() == GameOutcome.ONGOING, (
        "Game must not end at turn 35 when max_turns=50"
    )
    board.turn = 50
    assert rules.check_game_status() == GameOutcome.THIEF_WIN


def test_rules_engine_enforces_minimum_35_turns():
    """Even if caller passes max_turns < 35, engine must use at least 35."""
    board = Board(cop_position=[0, 0], thief_position=[6, 6])
    rules = RulesEngine(board, max_turns=5)
    assert rules.max_turns == 35, "max_turns must be clamped to minimum 35"


# ---------------------------------------------------------------------------
# Config: shared config has required physics sections
# ---------------------------------------------------------------------------


def _load_game_config() -> dict:
    """Load the [game.*] sections from cop/config.toml."""
    import tomllib
    config_path = Path("cop/config.toml")
    assert config_path.exists(), "cop/config.toml must exist"
    with open(config_path, "rb") as f:
        raw = tomllib.load(f)
    game = raw.get("game", {})
    assert game, "cop/config.toml must contain [game.*] sections"
    return game


def test_shared_config_has_required_sections():
    """cop/config.toml must contain all mandatory shared-physics game sections."""
    cfg = _load_game_config()
    assert "board_and_agents" in cfg, "Missing [game.board_and_agents]"
    assert "movement_and_barriers" in cfg, "Missing [game.movement_and_barriers]"
    assert "scoring" in cfg, "Missing [game.scoring]"
    assert "pheromones" in cfg, "Missing [game.pheromones]"
    assert "network_and_league" in cfg, "Missing [game.network_and_league]"
    assert "rate_limiter_gatekeeper" in cfg, "Missing [game.rate_limiter_gatekeeper]"


def test_shared_config_no_private_sections():
    """The [game.*] sections must NOT contain private settings like reports."""
    cfg = _load_game_config()
    assert "reports" not in cfg, "[reports] must be outside [game.*], not inside it"


def test_shared_config_barrier_quota_minimum():
    cfg = _load_game_config()
    bq = cfg.get("movement_and_barriers", {}).get("max_barriers", 0)
    assert bq >= 14, f"max_barriers must be >= 14, got {bq}"


def test_shared_config_max_turns_minimum():
    cfg = _load_game_config()
    mt = cfg.get("movement_and_barriers", {}).get("max_moves", 0)
    assert mt >= 35, f"max_moves must be >= 35, got {mt}"


def test_shared_config_scent_fixed_values():
    cfg = _load_game_config()
    ph = cfg.get("pheromones", {})
    assert ph.get("pheromone_center_intensity") == pytest.approx(0.9), (
        "pheromone_center_intensity must be fixed at 0.9"
    )
    assert ph.get("pheromone_decay") == pytest.approx(0.10), (
        "pheromone_decay must be fixed at 0.10"
    )
    assert ph.get("pheromone_grid_size") == 5, "pheromone_grid_size must be fixed at 5"


# ---------------------------------------------------------------------------
# Gmail: send-only scope
# ---------------------------------------------------------------------------


def test_gmail_auth_scope_send_only():
    """gmail_auth.py must request only gmail.send, not gmail.compose."""
    auth_path = Path("scripts/gmail_auth.py")
    content = auth_path.read_text(encoding="utf-8")
    assert "gmail.compose" not in content, "gmail_auth.py must not request gmail.compose scope"
    assert "gmail.send" in content, "gmail_auth.py must request gmail.send scope"
