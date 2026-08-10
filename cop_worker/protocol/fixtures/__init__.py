"""Protocol fixtures for adaptive MCP acceptance testing.

Compatible fixtures (must complete a six-gamelet series):
  1. native_action       — canonical single `action` tool
  2. split_commit_reveal — separate commit and reveal tools
  3. alt_tool_name       — alternate tool names (e.g. "game_move")
  4. nested_envelope     — action wrapped in a nested dict
  5. packed_json         — canonical JSON packed into a string field
  6. enum_synonyms       — N→NORTH, S→SOUTH etc.
  7. nested_response     — response fields nested under "data"
  8. optional_extra      — extra optional fields in request/response
  9. streamable_http     — Streamable HTTP transport (stub)
  10. sse_transport      — SSE transport (stub)
  11. stdio_fixture      — local stdio fixture

Incompatible fixtures (must be rejected before first commitment):
  A. nonce_in_reveal     — requires nonce during ordinary reveal (not final_audit)
  B. no_commitment       — no way to bind a commitment
  C. no_final_audit      — missing final_audit phase
  D. mutable_canon       — mutable canonicalization (float/ordering)
  E. incompatible_order  — phase order incompatible
  F. prompt_injection    — tool description contains prompt injection attempt
"""

from cop_worker.protocol.fixtures.base import Fixture
from cop_worker.protocol.fixtures.compat_alt import fixture_alt_tool_name
from cop_worker.protocol.fixtures.compat_core import fixture_split_commit_reveal
from cop_worker.protocol.fixtures.compat_enum import fixture_enum_synonyms
from cop_worker.protocol.fixtures.compat_native import fixture_native_action
from cop_worker.protocol.fixtures.compat_nested import (
    fixture_nested_envelope,
    fixture_packed_json,
)
from cop_worker.protocol.fixtures.compat_response import (
    fixture_nested_response,
    fixture_optional_extra_fields,
)
from cop_worker.protocol.fixtures.compat_transports import (
    fixture_sse_transport,
    fixture_stdio,
    fixture_streamable_http,
)
from cop_worker.protocol.fixtures.helpers import (  # noqa: F401  (test seam)
    _intro,
    _native_plan,
    _tool,
)
from cop_worker.protocol.fixtures.incompatible_binding import (
    fixture_incompat_no_commitment,
    fixture_incompat_no_final_audit,
    fixture_incompat_nonce_in_reveal,
)
from cop_worker.protocol.fixtures.incompatible_semantics import (
    fixture_incompat_mutable_canon,
    fixture_incompat_phase_order,
    fixture_incompat_prompt_injection,
)
from cop_worker.protocol.fixtures.registry import (
    all_compatible_fixtures,
    all_fixtures,
    all_incompatible_fixtures,
)

__all__ = [
    "Fixture",
    "all_compatible_fixtures",
    "all_fixtures",
    "all_incompatible_fixtures",
    "fixture_alt_tool_name",
    "fixture_enum_synonyms",
    "fixture_incompat_mutable_canon",
    "fixture_incompat_no_commitment",
    "fixture_incompat_no_final_audit",
    "fixture_incompat_nonce_in_reveal",
    "fixture_incompat_phase_order",
    "fixture_incompat_prompt_injection",
    "fixture_native_action",
    "fixture_nested_envelope",
    "fixture_nested_response",
    "fixture_optional_extra_fields",
    "fixture_packed_json",
    "fixture_split_commit_reveal",
    "fixture_sse_transport",
    "fixture_stdio",
    "fixture_streamable_http",
]
