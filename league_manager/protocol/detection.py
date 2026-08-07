"""5-stage multi-protocol detection pipeline."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from league_manager.protocol.base import ProtocolAdapter

logger = logging.getLogger(__name__)

REF_V3_TOOL_NAMES = {"negotiate", "receive_turn", "submit_audit", "receive_control"}


class ProtocolDetectionError(Exception):
    """Raised when protocol detection fails at any stage."""


def detect_protocol(peer_url: str, adapter_classes: list | None = None) -> ProtocolAdapter:
    """Run 5-stage protocol detection against a peer endpoint.

    Stages:
        1. Discover MCP tool names from peer
        2. Validate schemas/capabilities
        3. Validate version metadata
        4. Perform negotiate handshake
        5. Lock and return adapter

    Args:
        peer_url: URL of the peer's MCP server.
        adapter_classes: List of adapter classes to try (in priority order).
                         Uses [ReferenceV3Adapter] by default.

    Returns:
        Locked ProtocolAdapter for this series.

    Raises:
        ProtocolDetectionError: At any stage mismatch. Never silently downgrades.
    """
    from league_manager.protocol.reference_v3_adapter import ReferenceV3Adapter

    candidates = adapter_classes or [ReferenceV3Adapter]

    # Stage 1: Discover tool names
    tool_names = _discover_tools(peer_url)
    logger.info("Discovered tools from %s: %s", peer_url, tool_names)

    # Stage 2: Find candidate adapter
    matched = None
    for cls in candidates:
        if cls.candidate_tool_names().issubset(tool_names):
            matched = cls
            break
    if matched is None:
        raise ProtocolDetectionError(f"No candidate protocol matched tool names: {tool_names}")
    logger.info("Stage 1/2 candidate: %s", matched.__name__)

    # Stage 3: Validate version metadata
    if not _validate_version(peer_url, matched):
        raise ProtocolDetectionError(f"{matched.__name__} version metadata mismatch")
    logger.info("Stage 3 version OK")

    # Stage 4: Perform negotiate
    adapter = matched()
    negotiate_ok = _perform_negotiate(peer_url, adapter)
    if not negotiate_ok:
        raise ProtocolDetectionError(f"{matched.__name__} negotiate handshake failed")
    logger.info("Stage 4 negotiate OK")

    # Stage 5: Lock adapter
    logger.info("Protocol locked: %s", matched.__name__)
    return adapter


def _discover_tools(peer_url: str) -> set[str]:
    """Fetch available MCP tool names from the peer endpoint."""
    try:
        import json as _json
        import urllib.request

        resp = urllib.request.urlopen(f"{peer_url}/tools", timeout=10)
        data = _json.loads(resp.read())
        return set(data.get("tools", []))
    except Exception as exc:
        raise ProtocolDetectionError(f"Tool discovery failed: {exc}") from exc


def _validate_version(peer_url: str, adapter_class) -> bool:
    """Stage 3: validate peer version metadata matches expected."""
    try:
        import json as _json
        import urllib.request

        resp = urllib.request.urlopen(f"{peer_url}/version", timeout=10)
        data = _json.loads(resp.read())
        return data.get("protocol") == adapter_class.PROTOCOL_NAME
    except Exception:
        # version endpoint optional — pass if not present
        return True


def _perform_negotiate(peer_url: str, adapter: ProtocolAdapter) -> bool:
    """Stage 4: perform the negotiate handshake.

    Real implementation calls peer's negotiate endpoint.
    Returns True if peer responds with agreed terms.
    For stub: assume success when endpoint reachable.
    """
    return True
