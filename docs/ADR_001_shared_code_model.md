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

### Option B: Identically vendored `agent/domain/` directory

Copy the same `agent/domain/` directory into both repositories. Enforce byte-identity
via a CI hash manifest comparing SHA-256 of each file across repos.

**Pros:** No publish pipeline; works with current `uv` setup; changes visible in diff.  
**Cons:** Risk of divergence if one repo is edited without mirroring the other.

## Decision

**Option B — identically vendored `agent/domain/`.**

Rationale:
- Both repos use `uv` without a private package index.
- A publish pipeline adds substantial operational complexity not justified at this stage.
- Divergence risk is mitigated by:
  1. The cross-repo conformance test suite (`tests/test_domain_conformance.py`) which loads
     `tests/fixtures/transcript_vectors.json` (identical in both repos) and verifies outcomes.
  2. A future CI job that hashes `agent/domain/**/*.py` in both repos and fails if they differ.

## Consequences

- `agent/domain/__init__.py`, `types.py`, `transition.py`, and `config_validator.py` must
  be kept byte-identical between vibecode-cop and vibecode-thief.
- `tests/fixtures/transcript_vectors.json` must be byte-identical.
- Any domain change must be applied to both repos in the same commit batch.
- The CI hash manifest (to be added in Phase 11) will catch any unintentional drift.
- Mutable runtime state (boards, commits, reveals, nonces, logs) remains in each repo's
  own process — never shared.
