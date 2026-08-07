"""LeagueManager configuration loading and validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigValidationError(Exception):
    """Raised when config fails validation."""


def validate_group_id(group_id: str) -> None:
    """Validate group_id is exactly 8 alphanumeric characters.

    Args:
        group_id: The group identifier to validate.

    Raises:
        ConfigValidationError: If group_id is invalid.
    """
    if len(group_id) != 8:
        raise ConfigValidationError(f"group_id must be exactly 8 chars, got {len(group_id)}")
    if not re.fullmatch(r"[A-Za-z0-9]{8}", group_id):
        raise ConfigValidationError(f"group_id must be alphanumeric only, got {group_id!r}")


@dataclass
class NetworkConfig:
    """Network ports and URLs for league_manager."""

    port: int = 8000
    admin_port: int = 8080
    cop_url: str = "http://localhost:8001"
    thief_url: str = "http://localhost:8002"
    peer_url: str = "http://localhost:8000"


@dataclass
class MatchConfig:
    """Match settings."""

    counted: bool = False
    starting_role: str = "police"


@dataclass
class LeagueConfig:
    """Full league_manager configuration."""

    group_id: str = "vibecode"
    network: NetworkConfig = field(default_factory=NetworkConfig)
    match: MatchConfig = field(default_factory=MatchConfig)
    log_dir: str = "logs"
    report_dir: str = "reports"

    def __post_init__(self) -> None:
        """Validate group_id on construction."""
        validate_group_id(self.group_id)


def load_config(path: str | Path) -> LeagueConfig:
    """Load and validate a league_manager YAML config file.

    Args:
        path: Path to the YAML config file.

    Returns:
        Validated LeagueConfig instance.

    Raises:
        ConfigValidationError: If config is invalid.
        FileNotFoundError: If config file does not exist.
    """
    data = yaml.safe_load(Path(path).read_text())
    net_data = data.get("network", {})
    match_data = data.get("match", {})
    network = NetworkConfig(**{k: v for k, v in net_data.items() if hasattr(NetworkConfig, k)})
    match = MatchConfig(**{k: v for k, v in match_data.items() if hasattr(MatchConfig, k)})
    return LeagueConfig(
        group_id=data.get("group_id", "vibecode"),
        network=network,
        match=match,
        log_dir=data.get("output", {}).get("log_dir", "logs"),
        report_dir=data.get("output", {}).get("report_dir", "reports"),
    )
