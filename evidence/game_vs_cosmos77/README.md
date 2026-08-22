# Counted game 10 — cosmos77-vs-vibecode — 47-47 SERIES TIE

- **Settled:** 2026-08-23 00:24-00:27 Israel time; six windows, **6/6 Verified OK**,
  all survivals (rows 45-45, Appendix-F series-tie aggregate **47-47**), `series_tie: true`.
- **game_uid:** `06f81d92-73bb-2426-9013-3d6ca94c2c4a` (unlabeled by written bilateral
  agreement; shared with the 2026-08-22 friendly — distinguishability lives in the
  counted accounting, recipients, and timestamps, accepted in writing by both teams).
- **Report:** emailed ONLY to the league address, gmail id `1a02b5f8c431cfb2`
  (2026-08-23 00:27:57+03:00). `games_played_including_this: vibecode 10, cosmos77 2`.
- **mutual_agreement.sha256:** `3601bd73a06b83d757072a923e036f01d325d0a821d09c7dd12c8e9c0affa803`,
  `confirmed: true` both sides. NOTE: byte-equal to the friendly's mutual sha — the
  five-key consensus rows are identical across the two series (same outcome pattern);
  this collision property was first documented in the bestteam pairing.
- **Sealed commits (every row):** vibecode cop `2915e7a1ad923bc8dbe510cc292262cda10fe9f2`,
  thief `a17af03ce0cadbd940bc5b01a9a8bc138733c06b`; cosmos77 cop
  `b8508a86c2117a7038970966a205b35a8c2b9cc3`, thief `a7d3a5b43553184d0adc001fc7a24b631142edc1`.
  All four were frozen/amended in the written ceremony (three declared amendments on our
  cop, each mailed before doors; their mail's first cop-sha cite was hand-mangled and
  corrected in writing against the wire-sealed value).
- **This repo played police** (even windows g02/g04/g06) — those gamelets' config+log+record
  are here; the thief repo holds g01/g03/g05.

## The night's engineering trail (three void attempts before the clean run)

1. 22:42 and 23:16 attempts: sg1 died (`receive_turn` McpError ×N → 404), settlement
   guard withheld at 5/6 both times; both discarded in writing by both teams. cosmos77's
   proposal to file the 5/6 with a zeroed window 1 (which would have scored 40-35 to
   them) was declined; their claim that our engine co-signed such a consensus was
   refuted from our artifact (`confirmed: false`, different sha, no window-1 row).
2. Root causes closed in order: our squeeze walls could seal the cop out of the thief's
   region (fix: BFS self-cutoff guard, cop `5c51cd9`); our 120s greeting-wait vs their
   instant seal + signed 30s turn clock (fix: `agreement_poll_sec = 10`); their standing
   shell / port handover owning sg1's first session (fix: arm-first ordering — they arm
   and dial at our closed doors, then one bounce); our search's flat SURVIVAL leaf
   degrading beyond-horizon play to first-legal-move tie-breaks (fix: cop-only graded
   leaf + 18s turn budget, cop `2915e7a`, thief search byte-identical by pin).
3. The clean run: attempt 4, first sg1 settlement of the pairing, six windows in ~3.5
   minutes, no failures, report filed at settlement.
