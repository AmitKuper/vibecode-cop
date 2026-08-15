# ADR-001: Shared Domain Code Distribution Model

**Date:** 2026-08-03  
**Status:** Accepted  
**Phase:** 1

## Context

The binding rules require that both repositories implement identical physics:
every transition, capture, scent update, and outcome must match across cop and thief.
We need a mechanism to distribute and enforce this shared logic while preserving
two fully independent OS processes with no shared mutable state.

Two options were evaluated:

### Option A: Versioned common package

Publish a `cop_thief_core` Python package on PyPI or a private index. Both repos
list it as a dependency and pin to the same version. Identity is enforced by the
locked hash in `uv.lock`.

**Pros:** Single authoritative source; version history; semantic versioning.  
**Cons:** Requires a publish pipeline; two-repo dependency bump cycle on every domain change.

### Option B: Identically vendored `<role>_worker/domain/` directory

Copy the same `<role>_worker/domain/` directory into both repositories. Enforce byte-identity
via a CI hash manifest comparing SHA-256 of each file across repos.

**Pros:** No publish pipeline; works with current `uv` setup; changes visible in diff.  
**Cons:** Risk of divergence if one repo is edited without mirroring the other.

## Decision

**Option B — identically vendored `<role>_worker/domain/`.**

Rationale:
- Both repos use `uv` without a private package index.
- A publish pipeline adds substantial operational complexity not justified at this stage.
- Divergence risk is mitigated by golden vectors: `conformance/test_conformance.py`
  replays `conformance/vectors/*.json` (scent model, commit construction, game-uid
  derivation, config validation) against the local domain code on every run, and both
  repositories are additionally pinned to the league kit's own frozen vectors, so a
  drift in either port fails a build before it can reach the wire.

## Consequences

- The domain package — `__init__.py`, `types.py`, `types_observation.py`,
  `types_records.py`, `transition.py`, `transition_geometry.py`, `transition_scent.py`,
  `runtime_transition.py`, `config_validator.py` — must be kept byte-identical between
  `vibecode-cop/cop_worker/domain/` and `vibecode-thief/thief_worker/domain/`.
- Any domain change must be applied to both repos in the same commit batch.
- Mutable runtime state (boards, commits, reveals, nonces, logs) remains in each repo's
  own process — never shared.
