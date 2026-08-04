"""Cop process entry point."""

import sys

from agent.role_cli import run_role_cli

if __name__ == "__main__":
    sys.exit(run_role_cli("cop"))
