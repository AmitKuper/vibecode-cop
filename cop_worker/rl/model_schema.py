"""Model schema versioning and validation for RL policies."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

CURRENT_OBSERVATION_SCHEMA_VERSION = "1.0"
CURRENT_ACTION_SCHEMA_VERSION = "1.0"
CURRENT_BELIEF_SCHEMA_VERSION = "1.0"

COP_ACTION_NAMES = ["N", "S", "E", "W", "STAY", "PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"]
THIEF_ACTION_NAMES = ["N", "S", "E", "W", "STAY"]


@dataclass
class ModelManifestEntry:
    role: str
    algorithm: str
    sha256: str
    training_code_sha: str
    config_sha256: str
    observation_schema_version: str
    action_schema_version: str
    belief_schema_version: str
    inference_mode: str  # "argmax"|"sample"|"low_temp"|"top_k_mix"
    grid_size: int
    artifact: str = ""
    architecture: str = ""
    cop_actions: list = field(default_factory=lambda: list(COP_ACTION_NAMES))
    thief_actions: list = field(default_factory=lambda: list(THIEF_ACTION_NAMES))
    random_seed: int = 42
    training_steps: int = 0
    hyperparams: dict = field(default_factory=dict)
    evaluation_win_rate: float = 0.0
    description: str = ""
    # Which observation the artifact was TRAINED on -- see cop_worker.rl.obs_mode.describe().
    # Keys: uniform_belief, wire_scent, decoded_scent. Recording this is what makes a
    # train/serve mismatch auditable instead of invisible: the manifest's 0.9608 cop was
    # trained on the unclamped trainer scent and scored 0.3185 on the real wire field, and
    # nothing in the manifest said so. Defaults to all-false = the legacy research
    # observation, which is what every pre-2026-08-09 checkpoint used.
    obs_mode: dict = field(default_factory=dict)

    def is_compatible(self, role: str, grid_size: int) -> tuple[bool, str]:
        """Returns (ok, reason)."""
        if self.role != role:
            return False, f"Model role {self.role!r} != required {role!r}"
        if self.grid_size != grid_size:
            return False, f"Model grid_size {self.grid_size} != config {grid_size}"
        if self.observation_schema_version != CURRENT_OBSERVATION_SCHEMA_VERSION:
            cur = CURRENT_OBSERVATION_SCHEMA_VERSION
            return False, f"obs schema {self.observation_schema_version} != {cur}"
        if self.action_schema_version != CURRENT_ACTION_SCHEMA_VERSION:
            cur = CURRENT_ACTION_SCHEMA_VERSION
            return False, f"action schema {self.action_schema_version} != {cur}"
        if self.belief_schema_version != CURRENT_BELIEF_SCHEMA_VERSION:
            cur = CURRENT_BELIEF_SCHEMA_VERSION
            return False, f"belief schema {self.belief_schema_version} != {cur}"
        return True, ""


class ModelLoadError(ValueError):
    pass


def load_manifest(path: str) -> dict:
    """Load models/MANIFEST.json, returns role->entry dict."""
    with open(path) as f:
        data = json.load(f)
    return {e["role"]: ModelManifestEntry(**e) for e in data["models"]}


def validate_model_file(path: str, expected_sha256: str) -> None:
    """Raise ModelLoadError if file hash doesn't match."""
    with open(path, "rb") as f:
        actual = hashlib.sha256(f.read()).hexdigest()
    if actual != expected_sha256:
        raise ModelLoadError(
            f"Model file {path}: hash mismatch. expected={expected_sha256} got={actual}"
        )
