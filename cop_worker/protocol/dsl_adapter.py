"""AdapterDSL: apply a validated transform pipeline to canonical payloads."""

from __future__ import annotations

import logging
from typing import Any

from cop_worker.protocol.dsl import (
    DSLTransform,
)

logger = logging.getLogger(__name__)


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
