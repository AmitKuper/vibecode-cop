"""Run the clean-tree two-process counted series, then verify its artifacts."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from verify_two_process.util import COP_REPO, THIEF_REPO, _free_port, _python, _wait_for_listener
from verify_two_process.verify import _verify_artifacts

# The original scripts/verify_local_two_process.py docstring — kept verbatim so
# the argparse --help description is byte-identical to the pre-split script.
_DESCRIPTION = (
    "Run and independently verify the real clean-tree two-process counted series."
)


def run(output: Path) -> dict:
    if not COP_REPO.is_dir() or not THIEF_REPO.is_dir():
        raise RuntimeError("companion cop/thief repositories were not found")
    for repo in (COP_REPO, THIEF_REPO):
        status = subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=repo,
            text=True,
        )
        if status.strip():
            raise RuntimeError(f"counted acceptance requires a clean repository: {repo}")
    cop_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=COP_REPO, text=True).strip()
    thief_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=THIEF_REPO, text=True
    ).strip()

    if output.exists():
        if any(output.iterdir()):
            raise RuntimeError(f"acceptance output directory is not empty: {output}")
    else:
        output.mkdir(parents=True)
    thief_port = _free_port()
    secret = "local-acceptance-shared-secret-2026"
    thief_stdout = (output / "thief_stdout.log").open("w", encoding="utf-8")  # noqa: SIM115
    thief_stderr = (output / "thief_stderr.log").open("w", encoding="utf-8")  # noqa: SIM115
    thief_env = {**os.environ, "GROUP_ID": "THIF1234"}
    cop_env = {**os.environ, "GROUP_ID": "COPP1234"}
    thief_cmd = [
        str(_python(THIEF_REPO)),
        "-m",
        "thief",
        "serve",
        "--mode",
        "counted",
        "--config",
        "thief/config.toml",
        "--host",
        "127.0.0.1",
        "--port",
        str(thief_port),
        "--peer-url",
        "http://127.0.0.1:1/mcp",
        "--secret",
        secret,
        "--games-dir",
        str(output / "thief"),
        "--acceptance-fake-gmail-outbox",
        str(output / "thief_fake_gmail.jsonl"),
    ]
    process = subprocess.Popen(
        thief_cmd,
        cwd=THIEF_REPO,
        env=thief_env,
        stdout=thief_stdout,
        stderr=thief_stderr,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        _wait_for_listener(thief_port, process)
        cop_cmd = [
            str(_python(COP_REPO)),
            "-m",
            "cop",
            "series",
            "--mode",
            "counted",
            "--config",
            "cop/config.toml",
            "--peer-url",
            f"http://127.0.0.1:{thief_port}",
            "--secret",
            secret,
            "--games-dir",
            str(output / "cop"),
            "--n-gamelets",
            "6",
            "--acceptance-fake-gmail-outbox",
            str(output / "cop_fake_gmail.jsonl"),
        ]
        completed = subprocess.run(
            cop_cmd,
            cwd=COP_REPO,
            env=cop_env,
            capture_output=True,
            text=True,
            timeout=240,
        )
        (output / "cop_stdout.log").write_text(completed.stdout, encoding="utf-8")
        (output / "cop_stderr.log").write_text(completed.stderr, encoding="utf-8")
        if completed.returncode != 0:
            raise RuntimeError(
                f"cop counted CLI failed with exit {completed.returncode}; "
                f"see {output / 'cop_stderr.log'}"
            )
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        thief_stdout.close()
        thief_stderr.close()
    return _verify_artifacts(output, cop_sha, thief_sha)


def main() -> int:
    parser = argparse.ArgumentParser(description=_DESCRIPTION)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--json", type=Path, help="optional summary JSON path")
    args = parser.parse_args()
    if args.output_dir:
        output = args.output_dir.resolve()
        result = run(output)
    else:
        output = Path(tempfile.mkdtemp(prefix="cop_thief_acceptance_"))
        result = run(output)
    result["output_dir"] = str(output)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0
