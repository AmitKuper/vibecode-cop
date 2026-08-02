"""Phase-0 subprocess startup smoke tests.

Each test spawns a fresh Python interpreter to verify that production entry
points import cleanly and that the CLI help command exits successfully.
"""

import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable
REPO = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, *cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=REPO,
    )


def test_peer_agent_runtime_import():
    result = _run(["-c", "import agent.peer_agent_runtime; print('OK')"])
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_cop_main_import():
    result = _run(["-c", "import cop.__main__; print('OK')"])
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_combined_entry_point_import():
    result = _run([
        "-c",
        "import agent.peer_agent_runtime; import cop.__main__; print('cop imports OK')",
    ])
    assert result.returncode == 0, result.stderr
    assert "cop imports OK" in result.stdout


def test_run_series_help():
    result = _run(["scripts/run_series.py", "--help"])
    assert result.returncode == 0, result.stderr
    assert "run_series" in result.stdout.lower() or "thief" in result.stdout.lower()


def test_language_hints_import():
    result = _run(["-c", "from agent.language.hints import generate_hint; print(generate_hint('NORTH'))"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()
