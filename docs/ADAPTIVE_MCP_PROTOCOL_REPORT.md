# Adaptive MCP Protocol Report — v11

## Status

The counted runtime performs protocol understanding before the first commitment and locks a
hashed `ProtocolProfile`. Gameplay then uses a deterministic adapter with
`per_turn_llm_calls == 0`. Incompatible semantics fail closed; discovery data never receives
real nonces, private signing keys, or authority over protected values.

## Course-native discovery pipeline

```text
TransportProbe -> MCPIntrospector -> ProtocolUnderstandingAgent (pre-game only)
-> declarative ProtocolMappingPlan -> StaticSemanticVerifier
-> safe placeholder conformance probes -> signed/hashed ProtocolProfile
-> DeterministicProtocolAdapter (gameplay, zero LLM calls)
```

The transport probe supports Streamable HTTP, SSE, and test-only stdio. Introspection sanitizes
prompt-injection-shaped tool descriptions and hashes the discovered schemas. The mapping DSL is
limited to identity, rename, nesting, canonical JSON packing, enum maps, extraction, affixes, and
integer/string conversion. The static verifier rejects missing lifecycle phases, absent
commitments, early nonce exposure, unsafe protected-field transforms, and invalid ordering.

Eight side-effect-free probes use placeholders only: schema validation, mapping completeness,
commitment binding, nonce isolation, protected-field integrity, phase ordering, idempotency, and
a placeholder commit/reveal/audit flow. A schema change invalidates the cached profile.

The real-process adaptive fixture matrix covers alternate names, split tools, nested envelopes,
packed JSON, enum synonyms, nested responses, optional fields, and changed transports. It also
rejects nonce leakage, absent commitments/audits, mutable canonical types, invalid ordering, and
prompt injection before the first counted commitment.

## Published league-kit `reference-v3` profile

The independent repository `Imreec/copthief-league-protocol` was cloned under `external/` and
left unmodified at commit `9cecfa8b4befa070dfee0f3bc23cfe7ff7216e8e`. Its complete Markdown,
source, generator, probe, test, workflow, and vector tree was reviewed. Its own documentation
correctly says that the course book remains authoritative; the kit pins cross-team byte and
delivery conventions.

This profile is deliberately separate from the course-native eight-phase mapping. Its exact MCP
surface is:

```text
negotiate(message)
receive_turn(message)
submit_audit(payload)
receive_control(message)
```

A half-turn is one push containing the commitment, hint, and scent field. The move and nonce are
not transmitted during play; both appear only in the bilateral audit reveal. Treating this as
renamed per-turn commit/reveal tools would leak the nonce and send the wrong message count.

`agent/adaptive/reference_v3.py` implements the kit's compact sorted native-UTF-8 canonical JSON,
`SHA256(canonical(payload) + "|" + nonce)`, the closed 14-key signed agreement, sorted game ID,
derived UUID, published scent/wire locks, commit-keyed duplicate handling, bounded reorder,
equivocation rejection, private audit records, and received-commit-to-reveal binding. Handlers
enqueue and return without blocking.

Executable evidence:

- all 113 published vectors pass without changing the external tree;
- the unmodified kit client called our real FastMCP server through all four tools;
- our discovered deterministic client called the unmodified kit server through all four tools;
- the locked profile hash is
  `4cc7609ea2690979e6e9776a391b2031bc838f66f306a3b2c04dadb02807decd`;
- `submit_audit(payload)` retains the kit's load-bearing argument asymmetry;
- gameplay protocol LLM calls are zero.

The kit's optional/proposed registrations remain negotiated rather than assumed. Omission is
playable where the published decision tables require it; two explicit incompatible declarations
are refused before gameplay.

## Security and production integration

`PeerRuntime._init_protocol_adapter()` completes discovery before `_send_start_game()` and binds
the resulting profile hash into Step-0 as `adapter_mapping_hash`. The runtime never silently
downgrades a counted incompatibility, never converts a peer violation into `STAY`, and verifies
protected fields byte-for-byte on every adapted request.

Public-tunnel play against another team remains `EXTERNAL_PENDING`; local real-process
bidirectional interoperability with the untouched published implementation is PASS.
