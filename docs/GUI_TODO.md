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

- [x] per-run history (2026-08-17): result artifacts were one-file-per-game_id
      and each series OVERWROTE the last - every friendly under a later counted
      game was lost as structured data. Fixed forward (every run now archives to
      results/history/, timestamped, never overwritten) and BACKFILLED: 17 lost
      per-run results recovered byte-exact from the sent report emails. The
      dashboard's friendly table now lists every run (16 friendlies).

- [x] WP9 screenshot-driven UI/UX review (2026-08-17): scripts/gui_snapshot.py
      captures every dashboard view headlessly (Edge, stable-size polling) to
      reports/gui_review/ for visual review. The pass caught one real data bug
      (settings displayed the stale base-config counted=1 instead of the
      ledger's 6) and one ordering bug (recovered-archive friendlies clustered
      at the table's tail; /api/hub/games now sorts newest-first). Layout
      polish: colored W/L record + recent-games table on Status, zebra rows,
      profile chips, replay board/step-card side by side, persistent play
      board (no layout jump). Suites green: cop 1782, thief 1177.

- [x] R7 user review round 2 (2026-08-17): six fixes from live user feedback.
      (1) play: N/S/E/W letter keys + Shift+direction barrier hotkeys, clearer
      legends; the hub now hands keyboard focus to the embedded frame — keys
      were going dead because the iframe never had focus. (2) history: bare
      "rotated" became "no replay (logs rotated)" with a tooltip saying why.
      (3) status: native 7x7 board (own pos ★ + belief red + sensed scent
      blue) replaces the 127.0.0.1 iframes, so it also renders when the
      dashboard is viewed remotely; /api/hub/live forwards the board fields
      (own knowledge only — never the opponent's coordinate). (4) replay: a
      game/window chip picker replaces the <select>. (5) replay names the
      group behind each role (COP x vs THIEF y + outcome + date) from the log
      summary. (6) dialects that seal no positions (anrbj666, rstabcde,
      uoh-sqak) are now dead-reckoned from their sealed moves + the fixed
      start cells — validated 288/288 against the dialects that also
      serialize state — so every replay shows BOTH roles and both scent
      fields, labelled "dead-reckoned" on the timeline. Suites green: thief
      1307, cop 1937 (2 pre-existing GPU-env failures, reproduced on master).

Decisions on record (2026-08-16, with the user):
- Panels: ALL extras (scent grid, hint+deception cue, integrity ticker).
- Replay: BOTH CLI stepping and web page, one shared core.
- Run policy: ALWAYS ON everywhere (counted included) => fail-open is a hard
  requirement; a busy port or dead GUI never touches play.
