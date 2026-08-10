"""Whitelist DSL for deterministic protocol field mapping.

Supported transforms (whitelist only — no arbitrary code execution):
  identity      — pass-through, no change
  rename        — rename a field key
  nest          — wrap value under a new dict key: {wrapper: value}
  unnest        — extract value from a dict: value = d[key]
  pack_json     — serialize value to canonical JSON string
  unpack_json   — deserialize value from JSON string
  base64_encode — base64-encode bytes/str value
  base64_decode — base64-decode str to bytes
  enum_map      — map enum value via lookup dict
  constant      — replace with a fixed constant (args: {"value": x})
  jmespath      — JMESPath extraction (subset: simple dot-paths only)
  validate_type — assert type matches expected (args: {"type": "str"/"int"/"dict"})
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_ALLOWED_TRANSFORMS = frozenset(
    [
        "identity",
        "rename",
        "nest",
        "unnest",
        "pack_json",
        "unpack_json",
        "base64_encode",
        "base64_decode",
        "enum_map",
        "constant",
        "jmespath",
        "validate_type",
    ]
)


@dataclass
class DSLTransform:
    """One transform in the mapping pipeline."""

    name: str
    args: dict[str, Any]

    def __post_init__(self) -> None:
        if self.name not in _ALLOWED_TRANSFORMS:
            raise ValueError(f"DSL transform not in whitelist: {self.name!r}")

    def apply(self, value: Any) -> Any:
        if self.name == "identity":
            return value
        if self.name == "rename":
            return value
        if self.name == "nest":
            key = self.args.get("key", "data")
            return {key: value}
        if self.name == "unnest":
            key = self.args.get("key", "data")
            if isinstance(value, dict):
                return value.get(key, value)
            return value
        if self.name == "pack_json":
            return json.dumps(value, sort_keys=True, separators=(",", ":"))
        if self.name == "unpack_json":
            return json.loads(value) if isinstance(value, str) else value
        if self.name == "base64_encode":
            if isinstance(value, str):
                value = value.encode()
            return base64.b64encode(value).decode()
        if self.name == "base64_decode":
            return base64.b64decode(value)
        if self.name == "enum_map":
            mapping = self.args.get("mapping", {})
            return mapping.get(str(value), value)
        if self.name == "constant":
            return self.args.get("value")
        if self.name == "jmespath":
            path = self.args.get("path", "")
            return _simple_jmespath(value, path)
        if self.name == "validate_type":
            expected = self.args.get("type", "any")
            if expected != "any" and not _check_type(value, expected):
                raise TypeError(
                    f"DSL validate_type: expected {expected}, got {type(value).__name__}"
                )
            return value
        return value


def _simple_jmespath(value: Any, path: str) -> Any:
    """Simple dot-path extraction (no wildcards, no filters)."""
    if not path:
        return value
    for key in path.split("."):
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return None
    return value


def _check_type(value: Any, expected: str) -> bool:
    type_map = {
        "str": str,
        "string": str,
        "int": int,
        "integer": int,
        "float": float,
        "dict": dict,
        "list": list,
        "bool": bool,
        "bytes": bytes,
    }
    t = type_map.get(expected)
    return isinstance(value, t) if t else True


from cop_worker.protocol.dsl_adapter import AdapterDSL  # noqa: E402,F401  (re-export)
