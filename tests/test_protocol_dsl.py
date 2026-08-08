"""Fast unit tests for the whitelist protocol-mapping DSL (both package copies).

Pure transforms — no LLM, no network. Covers cop_worker.protocol.dsl and the
duplicated league_manager.protocol.dsl.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from cop_worker.protocol import dsl as cop_dsl
from league_manager.protocol import dsl as lm_dsl

MODULES = [cop_dsl, lm_dsl]


@dataclass
class _FM:
    canonical_field: str
    remote_field: str
    transform: str = "identity"
    transform_args: dict = None  # type: ignore[assignment]
    constant_value: object = None
    required: bool = False

    def __post_init__(self):
        if self.transform_args is None:
            self.transform_args = {}


@pytest.mark.parametrize("mod", MODULES)
def test_transform_whitelist_rejects_unknown(mod):
    with pytest.raises(ValueError, match="whitelist"):
        mod.DSLTransform("exec_arbitrary_code", {})


@pytest.mark.parametrize("mod", MODULES)
def test_core_transforms(mod):
    xf = mod.DSLTransform
    assert xf("identity", {}).apply("x") == "x"
    assert xf("nest", {"key": "w"}).apply(5) == {"w": 5}
    assert xf("unnest", {"key": "w"}).apply({"w": 9}) == 9
    assert xf("pack_json", {}).apply({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    assert xf("unpack_json", {}).apply('{"a":1}') == {"a": 1}
    assert xf("enum_map", {"mapping": {"N": "NORTH"}}).apply("N") == "NORTH"
    assert xf("constant", {"value": 42}).apply("ignored") == 42


@pytest.mark.parametrize("mod", MODULES)
def test_base64_roundtrip(mod):
    xf = mod.DSLTransform
    enc = xf("base64_encode", {}).apply("hello")
    assert xf("base64_decode", {}).apply(enc) == b"hello"


@pytest.mark.parametrize("mod", MODULES)
def test_validate_type(mod):
    xf = mod.DSLTransform
    assert xf("validate_type", {"type": "str"}).apply("ok") == "ok"
    with pytest.raises(TypeError):
        xf("validate_type", {"type": "int"}).apply("not-an-int")


@pytest.mark.parametrize("mod", MODULES)
def test_jmespath_dot_path(mod):
    xf = mod.DSLTransform
    assert xf("jmespath", {"path": "a.b"}).apply({"a": {"b": 7}}) == 7
    assert xf("jmespath", {"path": "a.b"}).apply({"a": 5}) is None
    assert xf("jmespath", {"path": ""}).apply({"a": 1}) == {"a": 1}


@pytest.mark.parametrize("mod", MODULES)
def test_adapter_apply_all_and_constructors(mod):
    adapter = mod.AdapterDSL.from_spec([{"name": "nest", "args": {"key": "d"}}])
    assert adapter.apply_all(3) == {"d": 3}
    assert mod.AdapterDSL.identity().apply_all("z") == "z"


@pytest.mark.parametrize("mod", MODULES)
def test_map_message_rename_constant_and_nesting(mod):
    mappings = [
        _FM("game_id", "match_id"),
        _FM("phase", "kind.name"),  # nested destination
        _FM("version", "v", constant_value="1.0"),
        _FM("missing", "x", required=True),  # dropped: absent + required
    ]
    out = mod.AdapterDSL().map_message({"game_id": "g1", "phase": "commit"}, mappings)
    assert out["match_id"] == "g1"
    assert out["kind"] == {"name": "commit"}
    assert out["v"] == "1.0"
    assert "x" not in out


@pytest.mark.parametrize("mod", MODULES)
def test_map_message_protected_values_restored(mod):
    mappings = [_FM("commitment", "commitment")]
    out = mod.AdapterDSL().map_message(
        {"commitment": "tampered"}, mappings, protected_values={"commitment": "true-hash"}
    )
    assert out["commitment"] == "true-hash"
