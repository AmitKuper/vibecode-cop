"""Fast unit tests for the deterministic schema→protocol mapper (both copies).

Feeds the acceptance fixtures' introspection results through infer_mapping_plan.
No network, no LLM.
"""

from __future__ import annotations

import pytest

from cop_worker.protocol import fixtures as cop_fx
from cop_worker.protocol import schema_mapper as cop_sm
from league_manager.protocol import fixtures as lm_fx
from league_manager.protocol import schema_mapper as lm_sm

PAIRS = [(cop_sm, cop_fx), (lm_sm, lm_fx)]


@pytest.mark.parametrize("sm,fx", PAIRS)
def test_native_fixture_infers_compatible_plan(sm, fx):
    plan = sm.infer_mapping_plan(fx.fixture_native_action().introspection)
    assert plan.is_compatible()
    assert plan.phase_mappings  # at least one phase mapped
    assert not plan.capability_gaps


@pytest.mark.parametrize("sm,fx", PAIRS)
def test_infer_runs_on_every_fixture_without_error(sm, fx):
    for fixture in fx.all_fixtures():
        plan = sm.infer_mapping_plan(fixture.introspection)
        # verdict is always populated; is_compatible mirrors absence of gaps
        assert plan.is_compatible() == (not plan.capability_gaps)


@pytest.mark.parametrize("sm,fx", PAIRS)
def test_split_commit_reveal_maps_distinct_tools(sm, fx):
    plan = sm.infer_mapping_plan(fx.fixture_split_commit_reveal().introspection)
    tools = {m.phase: m.remote_tool for m in plan.phase_mappings}
    # commit and reveal should resolve to different remote tools in a split schema
    if "commit" in tools and "reveal" in tools:
        assert tools["commit"] != tools["reveal"]
