"""``ChebyshevScent`` must reproduce the kit's own ``subtractive_chebyshev_v1`` fixtures.

This class exists only to *measure* what our champions would score if a peer locks the
reference scent model instead of the book model they trained on. A measurement harness that
silently mis-implements the law under test is worse than no harness: it would produce a
confident win rate for a field nobody plays on. So every value here is checked against
``external/copthief-league-protocol/vectors/pheromone.json`` (status CORE) and against the
merge-by-max / deposit-then-decay ordering in ``sparring/rules/scent.py::Trail.full_turn``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from scripts.eval_policy_quality import ChebyshevScent

VECTORS = (
    REPO_ROOT.parent / "external" / "copthief-league-protocol" / "vectors" / "pheromone.json"
)


def _fixture() -> dict:
    if not VECTORS.exists():
        pytest.skip(f"kit vectors not present at {VECTORS}")
    return json.loads(VECTORS.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case_index", [0, 1])
def test_emission_matches_kit_pheromone_vectors(case_index: int) -> None:
    """Centre-of-board and clipped-corner emissions, both CORE fixtures."""
    case = _fixture()["emit"][case_index]
    cr, cc = case["center"]
    scent = ChebyshevScent(
        case["board_size"],
        field_size=case["grid_size"],
        emit_intensity=case["intensity"],
    )
    # Fixture centres are (row, col); emit() takes (x, y) == (col, row).
    got = {f"{r},{c}": v for (r, c), v in scent.emit((cc, cr)).items()}
    assert got == case["field"]


def test_decay_matches_kit_vectors() -> None:
    """Subtractive decay, rounded to 3 places, with a floor that deletes the cell."""
    for case in _fixture()["decay"]:
        scent = ChebyshevScent(7, decay_per_step=case["decay"])
        scent.thief = {
            (int(k.split(",")[0]), int(k.split(",")[1])): v for k, v in case["before"].items()
        }
        scent.intensity = 0.0  # deposit nothing; isolate the decay half of the turn
        scent.min_center = 1.0
        scent.update((0, 0), (0, 0))
        got = {f"{r},{c}": v for (r, c), v in scent.thief.items()}
        expected = {k: v for k, v in case["after"].items() if v > 0.0}
        assert got == expected


def test_peak_is_zero_point_eight_not_zero_point_nine() -> None:
    """Merge-by-max plus one decay caps the standing field at 0.8 -- imreeyal brief 3.13.

    If this were implemented with ``+=`` like the book model, a stationary emitter would climb
    past 0.9 and the whole point of the comparison would be lost.
    """
    scent = ChebyshevScent(7)
    for _ in range(20):
        scent.update((0, 0), (3, 3))
    assert max(scent.thief.values()) == pytest.approx(0.8)
    assert scent.thief[(3, 3)] == pytest.approx(0.8)


def test_argmax_localises_the_emitter() -> None:
    """The reason this field is *more* informative than the saturated book field."""
    scent = ChebyshevScent(7)
    for _ in range(15):
        scent.update((0, 0), (5, 2))
    grid = scent.observation_for("cop")
    flat = [(v, (y, x)) for y, row in enumerate(grid) for x, v in enumerate(row)]
    assert max(flat)[1] == (2, 5)  # (row, col) == (y, x) of the thief


def test_play_accepts_the_chebyshev_mode() -> None:
    """The mode must actually reach the policies, not silently fall through to 'train'."""
    from cop_worker.rl.research_evaluation import ScriptedResearchPolicy

    from scripts.eval_policy_quality import DeployedPolicy, play

    cop = DeployedPolicy("cop", "prod")
    thief = ScriptedResearchPolicy("thief", "random")
    winner, turns = play(cop, thief, 1234, 1, scent_mode="chebyshev")
    assert winner in ("cop", "thief")
    assert 1 <= turns <= 35
    # A chebyshev field never reads 0.9 after decay; proves the override was the new law.
    assert cop.scent_override is not None
    assert max(max(row) for row in cop.scent_override) <= 0.8
