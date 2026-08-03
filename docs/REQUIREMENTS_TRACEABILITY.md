# Requirements Traceability Matrix — vibecode-cop

**Last updated:** 2026-08-03 (Phase 0)

| Requirement | Spec Ref | Implementation | Test(s) | Status |
|-------------|----------|----------------|---------|--------|
| Trapped thief → COP_WIN (STAY excluded) | §3.4 | `Board.has_orthogonal_escape()`, `rules_outcomes.check_game_status()` | `TestTrappedThiefSemantics` (7) | PASS |
| Barrier on thief cell = legal capture | §5.2 | `agent/rl/env_helpers.apply_place_action()` | `TestBarrierOnThiefCapture` (4) | PASS |
| Empty audit → NOT_APPLICABLE | §7.1 | `agent/peer_audit.run_final_audit()` | `TestAuditCompleteness` (3) | PASS |
| Counted series = exactly 6 gamelets | League rule | `agent/game_series.COUNTED_GAMELETS`, `GameSeries.__init__()` | `TestExactlySixGamelets` (7) | PASS |
| Movement path = RL → heuristic only | §6.1 | `agent/peer_turn_helpers.select_move()` | `TestNoLLMMovementFallback` (2) | PASS |
| Live-view GUI always importable | Mandatory deliverable | `fastapi` in `pyproject.toml`, `webserver/routes/live_view.py` | `TestLiveViewRoleFiltering` (5) | PASS |
| Cop/thief views show only own position | §8.3 | `webserver/routes/live_view.live_cop_view()`, `live_thief_view()` | `TestLiveViewRoleFiltering` (5) | PASS |
| Peer audit hash-chain verification | §7.2 | `agent/peer_audit.run_final_audit()` | `TestPeerRuntimeNoCentralJudge` | PASS |
| Commitment scheme (commit→reveal→verify) | §7.3 | `agent/mcp/crypto.create_commitment()` | `TestAuditCompleteness::test_valid_commits_return_passed` | PASS |
| Series result written to disk | §9.1 | `agent/game_series.GameSeries.run_series()` | `TestGameSeriesSixGamelets::test_series_result_file_written` | PASS |
