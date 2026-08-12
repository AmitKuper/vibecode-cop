"""Variant dispatch and CLI entry point for the adaptive peer fixture server."""

from __future__ import annotations

import argparse

from fastmcp import FastMCP

from .common import _CALL_COUNTER, make_responder, register_conformance
from .variants_alt import ALT_VARIANTS
from .variants_broken import BROKEN_VARIANTS
from .variants_core import CORE_VARIANTS
from .variants_hostile import HOSTILE_VARIANTS
from .variants_transport import TRANSPORT_VARIANTS

_REGISTRY = {
    **CORE_VARIANTS,
    **ALT_VARIANTS,
    **TRANSPORT_VARIANTS,
    **BROKEN_VARIANTS,
    **HOSTILE_VARIANTS,
}


def _build_server(variant: str, nested_response: bool = False) -> FastMCP:
    mcp = FastMCP(name=f"fixture-{variant}")
    _CALL_COUNTER.clear()

    # All variants share the same conformance tool (hostile variants may
    # re-register it with a corrupted implementation, as before the split).
    register_conformance(mcp)

    registrar = _REGISTRY.get(variant)
    if registrar is None:
        raise ValueError(f"Unknown variant: {variant!r}")
    registrar(mcp, make_responder(nested_response), nested_response)
    return mcp


def main() -> None:
    """Parse args and start the fixture MCP server."""
    parser = argparse.ArgumentParser(description="Adaptive peer MCP fixture server")
    parser.add_argument("--variant", required=True)
    parser.add_argument("--transport", default="stdio", choices=["stdio", "http", "sse"])
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    nested = args.variant == "nested_response"
    mcp = _build_server(args.variant, nested_response=nested)

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "http":
        mcp.run(transport="streamable-http", host="127.0.0.1", port=args.port)
    elif args.transport == "sse":
        mcp.run(transport="sse", host="127.0.0.1", port=args.port)
