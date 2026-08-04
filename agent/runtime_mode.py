"""Runtime mode — controls fail-closed behavior."""

from enum import Enum


class RuntimeMode(Enum):
    COUNTED = "counted"  # fail-closed, all guards active
    WARMUP = "warmup"  # real transport, guards relaxed
    DEVELOPMENT = "development"  # in-process, safe fallbacks
