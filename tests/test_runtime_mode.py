from __future__ import annotations

import pytest

pytest.skip("module removed in restructure", allow_module_level=True)

"""Tests for RuntimeMode enum and AgentOrchestrator (Phase 1 v7)."""


import subprocess
import sys

import pytest

from cop_worker.runtime_mode import RuntimeMode

# ---------------------------------------------------------------------------
# 1. RuntimeMode values
# ---------------------------------------------------------------------------


def test_runtime_mode_values():
    assert RuntimeMode.COUNTED.value == "counted"
    assert RuntimeMode.WARMUP.value == "warmup"
    assert RuntimeMode.DEVELOPMENT.value == "development"


# ---------------------------------------------------------------------------
# 2. AgentOrchestrator — DEVELOPMENT mode
# ---------------------------------------------------------------------------


def test_orchestrator_development_init(tmp_path):
    from cop_worker.agent_orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(
        role="cop",
        game_uid="test-game-001",
        grid_size=7,
        mode=RuntimeMode.DEVELOPMENT,
        work_dir=str(tmp_path),
    )
    assert orch.role == "cop"
    assert orch.mode == RuntimeMode.DEVELOPMENT
    assert orch.grid_size == 7


# ---------------------------------------------------------------------------
# 3. COUNTED mode rejects dev secret
# ---------------------------------------------------------------------------


def test_orchestrator_counted_rejects_dev_secret(tmp_path):
    from cop_worker.agent_orchestrator import AgentOrchestrator

    with pytest.raises(ValueError, match="development/placeholder secret"):
        AgentOrchestrator(
            role="cop",
            game_uid="test-game-002",
            grid_size=7,
            mode=RuntimeMode.COUNTED,
            work_dir=str(tmp_path),
            config={"secret": "dev-secret-change-me", "model_sha256": "abc123"},
        )


# ---------------------------------------------------------------------------
# 4. COUNTED mode rejects placeholder model SHA
# ---------------------------------------------------------------------------


def test_orchestrator_counted_rejects_placeholder_model(tmp_path):
    from cop_worker.agent_orchestrator import AgentOrchestrator

    with pytest.raises(ValueError, match="placeholder/missing model SHA"):
        AgentOrchestrator(
            role="cop",
            game_uid="test-game-003",
            grid_size=7,
            mode=RuntimeMode.COUNTED,
            work_dir=str(tmp_path),
            config={"secret": "real-prod-secret-xyz", "model_sha256": "placeholder"},
        )


# ---------------------------------------------------------------------------
# 5. Legal mask — cop (9 elements)
# ---------------------------------------------------------------------------


def test_orchestrator_legal_mask_cop(tmp_path):
    from cop_worker.agent_orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(
        role="cop",
        game_uid="test-game-004",
        grid_size=7,
        mode=RuntimeMode.DEVELOPMENT,
        work_dir=str(tmp_path),
    )
    mask = orch.get_legal_mask(own_position=(3, 3), barriers=[], barriers_remaining=5)
    assert mask.shape == (9,)


# ---------------------------------------------------------------------------
# 6. Legal mask — thief (5 elements)
# ---------------------------------------------------------------------------


def test_orchestrator_legal_mask_thief(tmp_path):
    from cop_worker.agent_orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(
        role="thief",
        game_uid="test-game-005",
        grid_size=7,
        mode=RuntimeMode.DEVELOPMENT,
        work_dir=str(tmp_path),
    )
    mask = orch.get_legal_mask(own_position=(3, 3), barriers=[])
    assert mask.shape == (5,)


# ---------------------------------------------------------------------------
# 7. Heuristic move returns valid action name
# ---------------------------------------------------------------------------


def test_orchestrator_heuristic_move_returns_valid(tmp_path):
    from cop_worker.agent_orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(
        role="cop",
        game_uid="test-game-006",
        grid_size=7,
        mode=RuntimeMode.DEVELOPMENT,
        work_dir=str(tmp_path),
    )
    move = orch.select_move_heuristic(own_position=(0, 0), barriers=[], barriers_remaining=5)
    assert move in orch.get_action_names()


# ---------------------------------------------------------------------------
# 8. Hint generation returns a string
# ---------------------------------------------------------------------------


def test_orchestrator_hint_generation(tmp_path):
    from cop_worker.agent_orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(
        role="cop",
        game_uid="test-game-007",
        grid_size=7,
        mode=RuntimeMode.DEVELOPMENT,
        work_dir=str(tmp_path),
    )
    hint = orch.generate_hint("N", intent="truth")
    assert isinstance(hint, str)
    assert len(hint) > 0


# ---------------------------------------------------------------------------
# 9. get_journal creates a StepJournal
# ---------------------------------------------------------------------------


def test_orchestrator_journal_created(tmp_path):
    from cop_worker.agent_orchestrator import AgentOrchestrator

    from cop_worker.audit.step_journal import StepJournal

    orch = AgentOrchestrator(
        role="cop",
        game_uid="test-game-008",
        grid_size=7,
        mode=RuntimeMode.DEVELOPMENT,
        work_dir=str(tmp_path),
    )
    journal = orch.get_journal(1)
    assert isinstance(journal, StepJournal)
    # Calling again returns same instance
    assert orch.get_journal(1) is journal


# ---------------------------------------------------------------------------
# 10. --mode flag is present in run_series.py --help
# ---------------------------------------------------------------------------


def test_run_series_counted_flag_exists():
    result = subprocess.run(
        [sys.executable, "scripts/run_series.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert "--mode" in result.stdout, f"--mode not in help output:\n{result.stdout}"
