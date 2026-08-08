"""Fast unit tests for protocol acceptance fixtures (both package copies).

Iterating every fixture builder exercises the whole fixtures module with no
network and no LLM. Covers cop_worker.protocol.fixtures and the duplicated
league_manager.protocol.fixtures.
"""

from __future__ import annotations

import pytest

from cop_worker.protocol import fixtures as cop_fx
from league_manager.protocol import fixtures as lm_fx

MODULES = [cop_fx, lm_fx]


@pytest.mark.parametrize("mod", MODULES)
def test_fixture_counts_and_partition(mod):
    compatible = mod.all_compatible_fixtures()
    incompatible = mod.all_incompatible_fixtures()
    allf = mod.all_fixtures()
    assert len(allf) == len(compatible) + len(incompatible)
    assert len(compatible) == 11 and len(incompatible) == 6
    assert all(f.compatible for f in compatible)
    assert all(not f.compatible for f in incompatible)


@pytest.mark.parametrize("mod", MODULES)
def test_every_fixture_is_well_formed(mod):
    names = set()
    for f in mod.all_fixtures():
        assert f.name and isinstance(f.name, str)
        assert f.description and isinstance(f.description, str)
        assert isinstance(f.compatible, bool)
        # introspection is a real result carrying a list of tool schemas
        assert isinstance(f.introspection.tools, list)
        names.add(f.name)
    assert len(names) == len(mod.all_fixtures())  # names unique


@pytest.mark.parametrize("mod", MODULES)
def test_compatible_fixtures_expose_tools(mod):
    for f in mod.all_compatible_fixtures():
        assert len(f.introspection.tools) >= 1, f.name


@pytest.mark.parametrize("mod", MODULES)
def test_incompatible_fixtures_carry_rejection_reason(mod):
    for f in mod.all_incompatible_fixtures():
        assert not f.compatible
        assert f.reject_reason and isinstance(f.reject_reason, str), f.name
