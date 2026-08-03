# Known Deviations from Original Specification

## Phase 0.5 — Reproducible Green Quality Baseline

### DEV-001: Thief RL Observation Reverted to 4 Channels

**Status:** Intentional, non-blocking

**Description:** The thief RL observation was reverted from 5 channels back to 4 channels.
The 5th channel (`prev_cop_pos` velocity) was an experimental addition that broke
compatibility with all existing trained models. The canonical 4-channel observation is:
  - Channel 0: thief position (1-hot)
  - Channel 1: last-revealed cop position (1-hot)
  - Channel 2: barriers (1 where blocked)
  - Channel 3: turns remaining (normalized scalar)

**Impact:** Existing 5-channel thief checkpoint files are rejected by the channel validation
guard in `policy_loader.py`. Tests that require a compatible thief model skip automatically
when only 5-channel models are present in `models/`.

**Resolution:** Retrain the thief model using the current 4-channel environment.

---

### DEV-004: Scent Model is Additive (Unbounded)

**Status:** Intentional, confirmed by authoritative rules

**Description:** The scent update formula is `new = 0.9 * old + emission`. When the
thief remains near previously-scented cells, values can exceed 0.9 (the SCENT_CENTER
constant). This is the correct additive model per specification section 4.3:
`tau_ij(t+1) = max(0, (1-rho)*tau_ij(t) + Delta_tau_ij)`.

---

## Phase 0 — Spec Correction (2026-08-03)

The following deviations introduced in Phase 0.5 were **corrected** in Phase 0:

### CORRECTED: Empty Audit Vacuously Valid (was DEV-002)

The previous `KNOWN_DEVIATIONS.md` claimed empty audit was "confirmed by authoritative rules."
This was incorrect. The binding rule requires:
- `NOT_APPLICABLE` for zero-turn aborted handshakes (not counted, not reported as success).
- `PASSED` only when a non-empty expected step set is fully verified.

**Fix:** `run_final_audit()` now returns `(False, {audit_status: NOT_APPLICABLE})` for empty
commitment logs. Empty evidence can never produce a successful counted result.

### CORRECTED: Trapped Thief Never Triggering COP_WIN (was DEV-003)

The previous `KNOWN_DEVIATIONS.md` claimed STAY always prevented trapping. This was incorrect.
The binding rule (spec section 3.4): "A thief trapped with no legal move is also considered
captured." STAY does not count as an orthogonal escape from a surrounded cell.

**Fix:** `Board.has_orthogonal_escape(role)` checks only NORTH/SOUTH/EAST/WEST. A thief
surrounded on all four orthogonal sides is caught even if STAY remains available.

### CORRECTED: FastAPI Tests Skipped (was DEV-005)

The previous `KNOWN_DEVIATIONS.md` treated fastapi skip as intentional. The live-view GUI
is a mandatory deliverable, so its import tests must always run.

**Fix:** `fastapi` added to production dependencies. `pytest.importorskip("fastapi")` removed
from `tests/test_live_gui_role_filtering.py`.
