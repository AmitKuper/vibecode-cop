"""Cop process entry point — delegates to cop_worker MCP server."""

import sys

from cop_worker.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
