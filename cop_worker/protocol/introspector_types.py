"""Introspection types and prompt-injection sanitizers."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


_INJECTION_PATTERNS = [
    r"ignore\s+previous",
    r"disregard\s+(all|prior|above)",
    r"you\s+are\s+now",
    r"system\s*:\s*",
    r"<\|im_start\|>",
    r"\[\s*INST\s*\]",
    r"forget\s+(everything|all)",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def _sanitize(text: str | None) -> str:
    text = text or ""
    if _INJECTION_RE.search(text):
        raise ValueError(f"Prompt injection detected in remote description: {text[:120]!r}")
    return text


def _sanitize_tree(value):
    """Recursively reject prompt-injection text while preserving full discovery data."""
    if isinstance(value, str):
        return _sanitize(value)
    if isinstance(value, list):
        return [_sanitize_tree(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_tree(item) for key, item in value.items()}
    return value


@dataclass
class ToolSchema:
    name: str
    description: str
    input_schema: dict
    output_schema: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    def schema_digest(self) -> str:
        blob = json.dumps(
            {
                "name": self.name,
                "input_schema": self.input_schema,
                "output_schema": self.output_schema,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(blob).hexdigest()[:16]


@dataclass
class IntrospectionResult:
    server_name: str
    server_version: str
    protocol_version: str
    tools: list[ToolSchema]
    resources: list[dict]
    prompts: list[dict]
    raw_capabilities: dict
    schema_digest: str

    def tool_names(self) -> list[str]:
        return [t.name for t in self.tools]

    def get_tool(self, name: str) -> ToolSchema | None:
        return next((t for t in self.tools if t.name == name), None)
