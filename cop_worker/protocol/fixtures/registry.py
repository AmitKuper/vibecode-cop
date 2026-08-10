"""Registry: every compatible and incompatible fixture, in canonical order."""

from __future__ import annotations

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


def all_compatible_fixtures() -> list[Fixture]:
    return [
        fixture_native_action(),
        fixture_split_commit_reveal(),
        fixture_alt_tool_name(),
        fixture_nested_envelope(),
        fixture_packed_json(),
        fixture_enum_synonyms(),
        fixture_nested_response(),
        fixture_optional_extra_fields(),
        fixture_streamable_http(),
        fixture_sse_transport(),
        fixture_stdio(),
    ]


def all_incompatible_fixtures() -> list[Fixture]:
    return [
        fixture_incompat_nonce_in_reveal(),
        fixture_incompat_no_commitment(),
        fixture_incompat_no_final_audit(),
        fixture_incompat_mutable_canon(),
        fixture_incompat_phase_order(),
        fixture_incompat_prompt_injection(),
    ]


def all_fixtures() -> list[Fixture]:
    return all_compatible_fixtures() + all_incompatible_fixtures()
