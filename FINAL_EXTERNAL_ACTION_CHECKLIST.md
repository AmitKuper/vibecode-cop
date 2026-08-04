# FINAL External Action Checklist — v9

Generated: 2026-08-04

All items below require action outside this session. Items are listed with their exact
status — nothing is marked done unless it is actually done.

## E-01: Real-Process Two-Process Integration Test

**Status**: EXTERNAL_PENDING

**What**: Run a full six-gamelet counted series between a real cop process and a real thief
process connected over TCP on localhost. Both processes must complete a `start_game →
commit → reveal → final_audit → result_agreement` cycle without any test mocking.

**How to run**:
```bash
# Terminal 1 (thief server)
cd vibecode-thief
uv run python -m agent.server --port 8001 --counted

# Terminal 2 (cop client)
cd vibecode-cop
uv run python -m agent.cli --opponent-url http://localhost:8001 --counted --series 6
```

**Acceptance criterion**: 6 gamelets complete, all commit-reveal bindings verified,
no ProtocolCompatibilityError, cop and thief commit files saved in agent/memory/.

---

## E-02: Competitive Tournament vs 8 Opponent Families

**Status**: EXTERNAL_PENDING

**What**: Run 8 opponent families × 50 series each against the trained cop policy.

**Families required**:
1. random (uniform random legal actions)
2. heuristic_pursuit (BFS toward thief)
3. heuristic_evasion (Manhattan distance maximization)
4. bfs_optimal (shortest-path cop)
5. minimax (depth-limited minimax)
6. mcts (Monte Carlo Tree Search)
7. previous_checkpoint (earlier PPO checkpoints)
8. mixed_population (random mix of above)

**Acceptance criterion**: Cop win rate >= 55% vs heuristic family.

**Current evidence**: Selfplay win rate 52% at 25k steps (code-verifiable).
Promotion threshold (55%) not yet reached externally.

---

## E-03: Release Tag Pushed to GitHub

**Status**: EXTERNAL_PENDING

**What**: Tag both repos with a `v9.0` (or `v9.x`) release tag and push to GitHub.

**Commands**:
```bash
# vibecode-cop
git tag -a v9.0 -m "v9: Adaptive MCP pipeline + 25k PPO training"
git push origin v9.0

# vibecode-thief
cd ../vibecode-thief
git tag -a v9.0 -m "v9: Adaptive MCP pipeline (symmetric)"
git push origin v9.0
```

**Acceptance criterion**: Tags appear on GitHub, both repos have identical `agent/adaptive/`
package at the tagged commit.

---

## E-04: Commit All Changes and Push

**Status**: EXTERNAL_PENDING (requires user to push)

All code changes from this session are ready to commit. The following changes need to be
staged, committed, and pushed:

**vibecode-cop changes**:
- `agent/adaptive/` package (12 files — full adaptive MCP pipeline)
- `agent/peer_runtime.py` (wired adaptive negotiation, profile_hash in Step-0)
- `tests/test_adaptive_mcp_v9.py` (79 adaptive MCP tests)
- `scripts/verify_100_readiness.py` (executable verifier)
- `results/score_100_verification.json` (verification report)
- `docs/SCORE_100_RUBRIC.json` (frozen rubric)
- `docs/RL_TOURNAMENT_REPORT.md` (updated with real training metrics)
- `docs/ADAPTIVE_MCP_PROTOCOL_REPORT.md` (new)
- `models/MANIFEST.json` (updated: real SHA256, training_steps=25000)
- `FINAL_100_READINESS_REPORT.md` (updated)
- `FINAL_EXTERNAL_ACTION_CHECKLIST.md` (this file, updated to v9)
- `FINAL_RELEASE_MANIFEST.json` (new)

**vibecode-thief changes**:
- `agent/adaptive/` package (12 files — synchronized copy)
- `agent/peer_runtime.py` (synchronized)

```bash
# Example commit commands
cd vibecode-cop
git add agent/adaptive/ agent/peer_runtime.py tests/test_adaptive_mcp_v9.py \
    scripts/verify_100_readiness.py results/ docs/ models/MANIFEST.json \
    FINAL_*.md FINAL_*.json
git commit -m "v9: Adaptive MCP pipeline, 25k PPO training, 79 acceptance tests"
git push

cd ../vibecode-thief
git add agent/adaptive/ agent/peer_runtime.py
git commit -m "v9: Sync adaptive MCP pipeline from cop"
git push
```
