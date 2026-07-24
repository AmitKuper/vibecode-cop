"""crewAI tool: read a Python skill file for review/validation."""

import ast
import logging
from pathlib import Path

from crewai.tools import tool

logger = logging.getLogger(__name__)


@tool
def read_skill_file(path: str) -> str:
    """Read a Python skill file and return its source plus a syntax check.

    Use this to review a generated MCP skill module before confirming it is
    ready. The response includes the full source code and a syntax verdict so
    you can spot errors without running the file.

    Args:
        path: Path to the Python skill file (absolute or project-relative).

    Returns:
        JSON-like string with keys:
          - path: resolved absolute path
          - source: complete file content
          - syntax_ok: true if ast.parse succeeds, false otherwise
          - syntax_error: error message when syntax_ok is false
          - has_start_game: true if a top-level 'start_game' function exists
          - has_action: true if a top-level 'action' function exists
          - has_ping: true if a top-level 'ping' function exists
    """
    import json

    target = Path(path)
    if not target.exists():
        return json.dumps({"error": f"File not found: {path}"})

    source = target.read_text(encoding="utf-8")

    syntax_ok = True
    syntax_error = ""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        syntax_ok = False
        syntax_error = str(exc)
        tree = None

    has_start_game = has_action = has_ping = False
    if tree:
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                if node.name == "start_game":
                    has_start_game = True
                elif node.name == "action":
                    has_action = True
                elif node.name == "ping":
                    has_ping = True

    logger.info(
        f"[read_skill_file] {target.name}: syntax_ok={syntax_ok} "
        f"start_game={has_start_game} action={has_action} ping={has_ping}"
    )

    return json.dumps(
        {
            "path": str(target.resolve()),
            "source": source,
            "syntax_ok": syntax_ok,
            "syntax_error": syntax_error,
            "has_start_game": has_start_game,
            "has_action": has_action,
            "has_ping": has_ping,
        },
        indent=2,
    )
