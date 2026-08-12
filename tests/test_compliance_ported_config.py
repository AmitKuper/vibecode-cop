"""Compliance tests verifying mandatory project rules (shared config and Gmail scope)."""

from pathlib import Path

import pytest

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
    assert ph.get("pheromone_decay") == pytest.approx(0.10), "pheromone_decay must be fixed at 0.10"
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
