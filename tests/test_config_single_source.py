"""Drift guard: config/game.json is the single source of truth.

Enforces that the wire terms, the physics constants, and the exchanged hashes all agree with
config/game.json — so a change in one place cannot silently diverge from the others.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cop_worker.config_loader import CONFIG_DIR, load_config, load_game, resolve_profile_dir
from cop_worker.protocol.reference_v3 import (
    default_terms,
    derive_game_uid,
    terms_from_game,
)
from cop_worker.rules_engine import RulesEngine

GAME = load_game()


def test_default_terms_match_game_json():
    # terms used on the wire == terms derived from the constitution (no drift)
    assert default_terms() == terms_from_game(GAME)


def test_config_sha256_is_whole_file_and_pinned():
    canon = json.dumps(GAME, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    sha = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    # Whole-file canonical hash of the IMREEYAL-pairing constitution (2026-08-10):
    # their game.json + pheromones.pheromone_min_center_intensity (the reference
    # schema-1.3 key spelling their loader reads — their 3.1 answer; the kit's FLAT
    # terms still carry bare `min_center_intensity: 0.5`, unchanged). This exact value
    # was independently computed by imreeyal — byte-agreement in writing pre-window.
    assert sha == "3b5c4a9a05c923acfe50ff355f56d4f529279435d87093aba6bad94015684f27"
    # ref3_artifacts computes the same
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import ref3_artifacts

    assert ref3_artifacts.config_sha256() == sha


def test_game_uid_pinned_vs_anrbj666():
    # Unchanged by the imreeyal reconciliation: proves the flat terms did not move.
    uid = derive_game_uid(default_terms(), "vibecode", "anrbj666")
    assert uid == "b2a16946-2cad-909f-60aa-b0cc8a8b7c4f"


def test_game_uid_pinned_vs_imreeyal():
    uid = derive_game_uid(default_terms(), "vibecode", "imreeyal")
    assert uid == "2e167349-f579-0201-e3f1-5ea0d75710c0"


def test_physics_constants_match_game_json():
    # The locked scent model constants must equal the constitution's pheromone values.
    pher = GAME["pheromones"]
    assert pher["pheromone_center_intensity"] == RulesEngine.SCENT_CENTER
    # SCENT_DECAY is the multiplicative retention = 1 - decay_per_step
    assert abs(RulesEngine.SCENT_DECAY - (1.0 - pher["pheromone_decay"])) < 1e-9


def test_config_loader_profile_resolution():
    assert resolve_profile_dir(None) == CONFIG_DIR
    cfg = load_config()
    assert set(cfg["runtime"]) >= {"network", "timeouts", "llm", "identity", "report"}
    # unknown profile name falls back to base config dir (never crashes)
    assert resolve_profile_dir("no-such-opponent") == CONFIG_DIR


def test_runtime_toml_has_no_league_address():
    # Safety: the league/counted address must never be stored in runtime config.
    txt = (CONFIG_DIR / "runtime.toml").read_text(encoding="utf-8")
    assert "rmisegal" not in txt
    assert "@gmail.com" in txt  # our own inbox is fine
