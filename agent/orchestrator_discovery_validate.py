"""Skill validation helpers for discovery."""

from __future__ import annotations

import ast
import json
import logging
import re
from pathlib import Path

from agent.orchestrator_discovery_render import _MAX_VALIDATION_ATTEMPTS

logger = logging.getLogger(__name__)


def python_validate_skill(skill_path: Path) -> tuple[bool, list[str]]:
    issues: list[str] = []
    try:
        source = skill_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except SyntaxError as exc:
        return False, [f"SyntaxError: {exc}"]
    except FileNotFoundError:
        return False, ["File not found"]
    names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
    }
    for required in ("start_game", "action", "ping"):
        if required not in names:
            issues.append(f"Missing function: {required}")
    return len(issues) == 0, issues


def run_validator_crew(role: str, llm: object, skill_path: Path) -> tuple[bool, list[str]]:
    try:
        from crewai import Crew

        from agent.agents.mcp_explorer_agent import (
            create_skill_validator_agent,
            create_skill_validator_task,
        )

        validator = create_skill_validator_agent(llm=llm)
        v_task = create_skill_validator_task(validator)
        crew = Crew(agents=[validator], tasks=[v_task], verbose=False)
        result = crew.kickoff(inputs={"skill_path": str(skill_path)})
        raw = result.raw if hasattr(result, "raw") else str(result)
        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group())
                valid = bool(data.get("valid", False))
                issues = data.get("issues", [])
                logger.info(f"[{role}] Validator verdict: {data.get('verdict', raw[:80])}")
                return valid, issues
        except Exception as exc:
            logger.debug(f"[{role}] Could not parse validator JSON: {exc}")
    except Exception as exc:
        logger.warning(f"[{role}] Validator crew error: {exc}")
    return python_validate_skill(skill_path)


def validate_skill_loop(
    role: str,
    llm: object,
    game_id: str,
    skill_path: Path,
    transport_url: str,
    probe_schemas: dict,
    explorer_raw: str,
    protocol_def: dict | None,
    write_skill_fn,
) -> Path:
    for attempt in range(1, _MAX_VALIDATION_ATTEMPTS + 1):
        try:
            verdict, issues = run_validator_crew(role, llm, skill_path)
        except Exception as exc:
            logger.warning(f"[{role}] Validator error on attempt {attempt}: {exc}")
            break
        if verdict:
            logger.info(f"[{role}] Skill validation PASSED on attempt {attempt}.")
            break
        logger.warning(
            f"[{role}] Skill validation FAILED on attempt {attempt}: {issues}. Regenerating…"
        )
        write_skill_fn(skill_path, transport_url, probe_schemas, explorer_raw, protocol_def)
    else:
        logger.error(f"[{role}] Skill still invalid after {_MAX_VALIDATION_ATTEMPTS} attempts.")
    return skill_path
