# TODO — Live GUI and Replay Viewer (cop repo)

Status legend: [ ] open · [~] in progress · [x] done (with date)

- [x] WP1 view model: extended SafeLiveView + real values through publish_view (2026-08-16; context layer in scripts/ref3_match/gui_context.py, cop repo)
- [x] WP2 live page: five panels (banner/belief/scent/hint/ticker), SSE (2026-08-16)
- [x] WP3 shared replay verification core (2026-08-16; ref3_steps.py, proven on the real nis-yar1 counted log: 71 records Verified OK, 1-byte tamper -> TAMPERED)
- [x] WP4 CLI stepping (2026-08-16; scripts/replay_stepper.py - n/p/j over the shared core)
- [x] WP5 web /replay page (2026-08-16; picker+slider+verdicts, ?log= auto-load, path-traversal refused)
- [x] WP6 always-on defaults (2026-08-16; ports active in base config + PROFILE-INHERITANCE FIX: profiles replace the base wholesale, so gui ports now fall back to base in cli_config - without this the GUI silently vanished in every real game)
- [x] WP7 tests (2026-08-16; local-truth+fail-open+verdict units, and LIVE: full 6/6 series with both GUIs up, result identical to GUI-off baseline 90-30)
- [x] WP8 evidence (2026-08-16): live belief-heatmap screenshots for BOTH roles + replay Verified-OK over the real nis-yar1 counted log, all captured during a live series, in evidence/gui/; KNOWN_DEVIATIONS updated; mirrored + drift-gated (42 shared files)
      sibling repo + drift-gate entries

- [x] R6 dashboard (2026-08-17): persistent hub on :8780 - history table (all
      series, shas, replay links), live-panel embedding, replay reuse; verified
      against the real results tree (7 series listed, counted log Verified OK).

Decisions on record (2026-08-16, with the user):
- Panels: ALL extras (scent grid, hint+deception cue, integrity ticker).
- Replay: BOTH CLI stepping and web page, one shared core.
- Run policy: ALWAYS ON everywhere (counted included) => fail-open is a hard
  requirement; a busy port or dead GUI never touches play.
