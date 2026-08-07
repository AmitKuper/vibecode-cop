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


class AdapterDSL:
    """Applies a sequence of DSL transforms to a message dict.

    This is the deterministic mapping engine used during gameplay.
    No LLM is called.
    """

    def __init__(self, transforms: list[DSLTransform] | None = None) -> None:
        self._transforms = transforms or []

    def apply_all(self, value: Any) -> Any:
        for t in self._transforms:
            value = t.apply(value)
        return value

    @classmethod
    def identity(cls) -> AdapterDSL:
        return cls([DSLTransform("identity", {})])

    @classmethod
    def from_spec(cls, spec: list[dict]) -> AdapterDSL:
        return cls([DSLTransform(s["name"], s.get("args", {})) for s in spec])

    def map_message(
        self,
        canonical_msg: dict,
        field_mappings: list,
        protected_values: dict | None = None,
    ) -> dict:
        """Apply field-level mapping to produce a remote-schema message.

        protected_values: byte-exact values that the DSL cannot change.
        They are injected after mapping and verified for integrity.
        """
        result: dict = {}

        for fm in field_mappings:
            src_field = fm.canonical_field
            dst_field = fm.remote_field

            if fm.constant_value is not None:
                result[dst_field] = fm.constant_value
                continue

            value = canonical_msg.get(src_field)
            if value is None and fm.required:
                logger.warning("DSL: required field %r missing in canonical message", src_field)
                continue
            if value is None:
                continue

            # Apply transforms
            dsl = AdapterDSL.from_spec(
                [{"name": fm.transform, "args": fm.transform_args}]
                if fm.transform != "identity"
                else []
            )
            mapped_value = dsl.apply_all(value)

            # Handle nesting
            if "." in dst_field:
                parts = dst_field.split(".")
                d = result
                for p in parts[:-1]:
                    d = d.setdefault(p, {})
                d[parts[-1]] = mapped_value
            else:
                result[dst_field] = mapped_value

        # Inject and verify protected values
        if protected_values:
            for k, v in protected_values.items():
                if k in result and result[k] != v:
                    logger.error(
                        "DSL: protected field %r was corrupted — restoring correct value", k
                    )
                result[k] = v

        return result
