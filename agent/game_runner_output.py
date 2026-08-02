"""Output file generation helpers for GameRunner (result, log, config, declaration)."""

import contextlib
import hashlib
import json
import logging
import platform
import subprocess as _sp
from pathlib import Path

try:
    import psutil as _psutil
except ImportError:
    _psutil = None

from agent.board import Board

logger = logging.getLogger(__name__)


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _git_commit() -> str:
    with contextlib.suppress(Exception):
        return _sp.check_output(["git", "rev-parse", "HEAD"], stderr=_sp.DEVNULL).decode().strip()
    return "unknown"


def _ram_gb() -> float | None:
    if _psutil is None:
        return None
    with contextlib.suppress(Exception):
        return round(_psutil.virtual_memory().total / (1024**3), 2)
    return None


def _gpu_info() -> str | None:
    with contextlib.suppress(Exception):
        out = (
            _sp.check_output(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                stderr=_sp.DEVNULL,
                timeout=5,
            )
            .decode()
            .strip()
        )
        return out or None
    return None


async def generate_output_files(
    runner: object,
    game_id: str,
    state: dict,
    board: Board,
    gamelet: int = 1,
) -> None:
    """Generate required submission/report files in the game directory."""
    gd = runner._game_dir
    g = f"{gamelet:02d}"
    hw = platform.uname()

    # LLM model from runner or private config
    llm_model = getattr(runner, "llm_model", None)
    if llm_model is None:
        with contextlib.suppress(Exception):
            import tomllib

            with open("cop/config.toml", "rb") as f:
                llm_model = tomllib.load(f).get("llm", {}).get("model")

    write_json(
        gd / f"declaration_{game_id}.json",
        {
            "game_id": game_id,
            "config_sha256": runner.config_sha256,
            "cop_url": runner.cop_url,
            "thief_url": runner.thief_url,
            "protocol_version": "1.0",
            "group_id": runner.group_name,
            "git_commit": _git_commit(),
            "gamelet": gamelet,
            "hardware": {
                "os": hw.system,
                "hostname": hw.node,
                "cpu": hw.processor or hw.machine,
                "python": platform.python_version(),
                "ram_gb": _ram_gb(),
                "gpu": _gpu_info(),
            },
            "llm_model": llm_model,
            "token_budget": getattr(runner, "token_budget", None),
            "tokens": (
                getattr(runner, "_token_counter", None).summary()
                if getattr(runner, "_token_counter", None) is not None
                else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "llm_calls": 0}
            ),
            "created_at": state.get("created_at"),
            "ended_at": state.get("ended_at"),
        },
    )
    # Include full shared config so replay verifier has all agreed parameters
    try:
        from agent.config.shared_config import load_shared_config

        shared_config = load_shared_config()
    except Exception:
        shared_config = {}
    write_json(
        gd / f"config_{game_id}_g{g}.json",
        {
            "game_id": game_id,
            "game_number": g,
            "config_sha256": runner.config_sha256,
            "max_turns": runner.max_turns,
            "shared_config": shared_config,
        },
    )
    log_hash = _write_log_file(runner, gd, game_id, g)
    result_out = {
        "game_id": game_id,
        "config_sha256": runner.config_sha256,
        "winner": state.get("winner"),
        "cop_win_score": runner.cop_win_score,
        "thief_win_score": runner.thief_win_score,
        "final_step": state.get("final_step"),
        "abort_reason": state.get("abort_reason"),
        "audit_ok": state.get("audit_ok"),
        "cop_final_position": board.cop_position,
        "thief_final_position": board.thief_position,
        "ended_at": state.get("ended_at"),
        "log_sha256": log_hash,
    }
    result_json_str = json.dumps(result_out, indent=2)
    result_out["result_sha256"] = hashlib.sha256(result_json_str.encode()).hexdigest()
    write_json(gd / f"result_{game_id}.json", result_out)
    write_json(gd / "report_plugin_results.json", {"game_id": game_id, "plugins": []})
    logger.info(f"[GameRunner] Output files written for {game_id}")


def _write_log_file(runner: object, gd: Path, game_id: str, g: str) -> str:
    # _cop_nonces / _thief_nonces are populated after final_audit
    cop_nonces = getattr(runner, "_cop_nonces", {})
    thief_nonces = getattr(runner, "_thief_nonces", {})
    log_entries = []
    for step, cop_rev in runner._cop_reveals.items():
        thief_rev = runner._thief_reveals.get(step, {})
        log_entries.append(
            {
                "step": step,
                "gamelet": g,
                "cop_move": cop_rev.get("move"),
                "thief_move": thief_rev.get("move"),
                "cop_h_commit": runner._cop_commits.get(step),
                "thief_h_commit": runner._thief_commits.get(step),
                "cop_state_hash": cop_rev.get("state_hash"),
                "thief_state_hash": thief_rev.get("state_hash"),
                "cop_hint": cop_rev.get("hint"),
                "thief_hint": thief_rev.get("hint"),
                "cop_intent": cop_rev.get("intent"),
                "thief_intent": thief_rev.get("intent"),
                "cop_nonce": cop_nonces.get(step),
                "thief_nonce": thief_nonces.get(step),
            }
        )
    log_out = {
        "game_id": game_id,
        "game_number": g,
        "entries": sorted(log_entries, key=lambda x: x["step"]),
    }
    log_json_str = json.dumps(log_out, indent=2)
    log_hash = hashlib.sha256(log_json_str.encode()).hexdigest()
    (gd / f"log_{game_id}_g{g}.json").write_text(log_json_str, encoding="utf-8")
    logger.debug(f"Wrote log file for {game_id}")
    return log_hash


from agent.game_runner_reports import generate_reports  # noqa: F401, E402
