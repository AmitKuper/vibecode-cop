"""Compatibility shim — all implementation lives in cop_worker.protocol.pipeline."""

from cop_worker.protocol.pipeline import *  # noqa: F401,F403
from cop_worker.protocol.pipeline import (  # noqa: F401
    discover_reference_v3,
    run_adaptive_negotiation,
)
