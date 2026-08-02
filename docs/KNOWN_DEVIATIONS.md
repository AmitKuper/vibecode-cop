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

### DEV-002: Empty Final Audit is Vacuously Valid

**Status:** Intentional, confirmed by authoritative rules

**Description:** `run_final_audit()` returns `audit_ok=True` when no opponent commitments
were recorded (e.g., the game was aborted before any commits). The previous implementation
required `len(h_commits) > 0`, which made zero-turn games always fail audit.

**Rationale:** An empty commitment log cannot be falsified. Requiring non-empty commits
conflated "integrity verification" with "game completion verification".

---

### DEV-003: Thief Can Never Be Trapped by Barriers Alone

**Status:** Intentional, confirmed by authoritative rules

**Description:** `check_game_status()` uses `board.get_legal_moves("thief")` which
includes STAY. A COP_WIN from trapped detection only triggers when the thief has
absolutely no legal moves at all (impossible in current implementation since STAY is
always available unless the thief's cell itself is a barrier, which cannot happen).

---

### DEV-004: Scent Model is Additive (Unbounded)

**Status:** Intentional, confirmed by authoritative rules

**Description:** The scent update formula is `new = 0.9 * old + emission`. When the
thief remains near previously-scented cells, values can exceed 0.9 (the SCENT_CENTER
constant). This is the correct additive model per specification.

---

### DEV-005: fastapi Tests Skipped When fastapi Not Installed

**Status:** Intentional, by design

**Description:** `tests/test_live_gui_role_filtering.py` uses `pytest.importorskip("fastapi")`
at module level. The `fastapi` package is not in the core dependencies. These tests
pass when fastapi is installed and skip gracefully otherwise.
