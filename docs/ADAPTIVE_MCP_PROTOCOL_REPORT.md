# Adaptive MCP Protocol Report — v9

## Overview

The v9 adaptive MCP protocol pipeline replaces the previous per-turn `ProtocolAdapterCrew`
(which called an LLM on every game turn) with a pre-game deterministic pipeline that runs
once before gameplay begins.

**Key invariant**: `DeterministicProtocolAdapter.per_turn_llm_calls == 0` at all times.

## Pipeline

```
TransportProbe → MCPIntrospector → ProtocolUnderstandingAgent (LLM, ONCE)
→ ProtocolMappingPlan → StaticSemanticVerifier
→ ConformanceProbes → ProtocolProfile (signed + cached)
→ DeterministicProtocolAdapter (used during gameplay, no LLM)
```

### Stage 1: TransportProbe

Detects the remote MCP transport:
- **Streamable HTTP**: POST /mcp with initialize message, HTTP 200/202
- **SSE**: GET /sse, content-type: text/event-stream
- **STDIO**: Local process (for testing)
- **UNKNOWN**: Raises `ProtocolCompatibilityError`

### Stage 2: MCPIntrospector

Introspects remote server tools via `tools/list`. Security features:
- **Prompt injection detection**: `_INJECTION_RE` regex scans all tool descriptions for
  patterns like "ignore previous instructions", "you are now", etc.
- Any tool with injection in its description is dropped; if no safe tools remain,
  raises `ProtocolCompatibilityError`.
- Computes `schema_digest` (SHA-256[:16] of all tool names + schemas) for cache lookup.

### Stage 3: ProtocolUnderstandingAgent (LLM, ONCE)

Single pre-game LLM call to map remote tool schema to canonical protocol phases.
Falls back to a deterministic heuristic if LLM is unavailable.

Output: `ProtocolMappingPlan` with per-phase field mappings.

### Stage 4: StaticSemanticVerifier

Validates the mapping plan before any counted commitment:
- Verdict must not be INCOMPATIBLE
- All 5 required phases must be mapped: `start_game, commit, reveal, final_audit, result_agreement`
- Commit phase must have a commitment field (H(move‖nonce‖game_id…))
- Nonce must NOT appear in commit or reveal phases (only in final_audit)
- Protected fields (game_id, commitment, signature, config_sha256) must not use non-identity transforms
- Raises `ProtocolCompatibilityError` on any hard violation

### Stage 5: ConformanceProbes

8 non-mutating probes using placeholder values (no real secrets):
1. `schema_validation` — plan has required phases
2. `field_mapping_completeness` — commit + reveal phases mapped
3. `commitment_binding` — commitment field survives adapt_request
4. `nonce_isolation` — nonce not in commit/reveal output
5. `protected_field_integrity` — game_id, commitment preserved byte-for-byte
6. `phase_ordering` — all required phases instantiable
7. `idempotency_structure` — same input → same output (deterministic)
8. `placeholder_commit_reveal` — full placeholder commit→reveal without real secrets

### Stage 6: ProtocolProfile

Signed, hashed, cached profile:
- `plan_hash`: SHA-256 of the serialized `ProtocolMappingPlan`
- `profile_hash`: SHA-256 of endpoint + transport + schema_digest + plan_hash + timestamp
- Included in Step-0 declaration as `adapter_mapping_hash`
- Cached by `remote_schema_digest`; invalidated when schema changes

### Stage 7: DeterministicProtocolAdapter

Applies the mapping plan via a whitelist DSL during gameplay:
- Allowed transforms: `identity, rename, nest, unnest, pack_json, unpack_json, enum_map, extract, prefix, suffix, to_string, to_int`
- Protected fields verified byte-for-byte on every `adapt_request`
- No LLM calls — purely deterministic

## Fixture Results

### Compatible Fixtures (11) — all pass

| Fixture | Description | Verifier | Conformance |
|---------|-------------|---------|-------------|
| native_action | Canonical single `action` tool | PASS | PASS |
| split_commit_reveal | Separate commit/reveal tools | PASS | PASS |
| alt_tool_name | Alternate tool name (game_move) | PASS | PASS |
| nested_envelope | header/body envelope | PASS | PASS |
| packed_json | Canonical JSON packed as string | PASS | PASS |
| enum_synonyms | N→NORTH, S→SOUTH, etc. | PASS | PASS |
| nested_response | Response under `data.*` | PASS | PASS |
| optional_extra_fields | Extra optional fields | PASS | PASS |
| streamable_http | Streamable HTTP transport | PASS | PASS |
| sse_transport | SSE transport | PASS | PASS |
| stdio_fixture | Local stdio | PASS | PASS |

### Incompatible Fixtures (6) — all rejected before first commitment

| Fixture | Rejection Reason |
|---------|-----------------|
| incompat_nonce_in_reveal | Nonce in reveal phase — StaticSemanticVerifier rejects |
| incompat_no_commitment | No commitment field in commit — StaticSemanticVerifier rejects |
| incompat_no_final_audit | INCOMPATIBLE verdict + missing phase — StaticSemanticVerifier rejects |
| incompat_mutable_canon | Float step type — identified as semantic incompatibility |
| incompat_phase_order | Wrong phase ordering — identified as structural incompatibility |
| incompat_prompt_injection | Injection in tool description — MCPIntrospector _sanitize raises |

## Security Guarantees

1. **No per-turn LLM** — protocol mapping is frozen before the first commitment
2. **Nonce isolation** — nonce never appears in commit or reveal phase output
3. **Commitment binding** — commitment field always present and unchanged in commit phase
4. **Prompt injection defense** — malicious tool descriptions rejected at introspection time
5. **Protected field integrity** — game_id, commitment, config_sha256 verified byte-for-byte
6. **Counted mode fails closed** — ProtocolCompatibilityError raised, no silent fallback

## Integration with PeerRuntime

`PeerRuntime._init_protocol_adapter()` calls `run_adaptive_negotiation()` before
`_send_start_game()`. The resulting `ProtocolProfile.profile_hash` is embedded in the
Step-0 declaration as `adapter_mapping_hash`. The `DeterministicProtocolAdapter` is used
for all subsequent `adapt_request()` calls during gameplay.

## External Pending

- **Real-process six-gamelet series**: Requires two live processes connected over TCP.
  Not run in this session. (E-01: EXTERNAL_PENDING)
