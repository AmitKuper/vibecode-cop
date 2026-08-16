# Known Deviations from the Original Specification

Every entry below is a deviation that is **still true today** (2026-08-15), with
the file or artifact that proves it. Items that were once listed here and have
since become false were removed rather than reworded; see "No longer deviations"
at the end for what changed.

## Active deviations

### D1: Public reachability without a tunnel — DEMONSTRATED

The book mandates a tunnelling tool (ngrok/Cloudflare); its stated purpose (§2.4)
is NAT traversal for hosts that cannot be reached directly. We instead expose the
two role endpoints on a router-forwarded **static public IP** (cop 61224 /
thief 61223), so the requirement's purpose — public reachability — is met without
the tool. This was demonstrated across the internet in five counted cross-team
series (anrbj666, imreeyal, uoh-sqak, rstabcde, najamjad —
`results/counted_series.json`). ngrok remains
supported and opt-in per pairing (`[network] ingress = "ngrok"`,
`docs/NGROK_INGRESS.md`); the tunnel/facade topology is documented in
`docs/DEPLOYMENT_TUNNEL_RUNBOOK.md`.

### D2: Email report format

The result email sends the canonical result JSON as the body **plus** the same
bytes as a single named attachment, rather than the book's Appendix-A prose
listing. Approved by the lecturer's reference agent — evidence:
`evidence/Email_Report_Agent_conversation.jpeg`. The remaining artifact kinds are
published in the repositories and reached through the result's `links.github`
(rule 49).

### D3: Hardcoded own-inbox default recipient

`cop_worker/gmail/gatekeeper.py` hardcodes `RECIPIENT = "agentsorch@gmail.com"`
(our own inbox) as the default. This is a deliberate safety rail: the
league/lecturer address is stored **nowhere** in code or config — test-enforced by
`tests/test_config_single_source.py::test_runtime_toml_has_no_league_address` —
and enters only by hand via `--report-to` on counted day. An address the run
cannot reach cannot be mailed by accident.

### D4: 150-line module limit — seven files over

The project rule is ≤150 lines per module. Seven production modules exceed it
today (measured 2026-08-15):

| File | Lines | Why it is kept whole |
|---|---:|---|
| `cop_worker/domain/transition.py` | 340 | The single physical-law transition function, byte-pinned by the kit's vectors and mirrored byte-identically in the thief repo. Splitting it adds cross-repo drift risk with no cohesion gain. |
| `cop_worker/net_gateway.py` | 168 | One outbound-call policy object (deadline + at-least-once retry + backoff). |
| `scripts/ref3_match/subgame_turns.py` | 167 | One sub-game's turn loop; the source-inspection call-site pins in `tests/` assert its ordering. |
| `scripts/ref3_match/subgame_setup.py` | 160 | One sub-game's handshake/setup path. |
| `cop_worker/protocol/reference_v3/session.py` | 157 | One wire session object. |
| `scripts/ref3_match/subgame_settle.py` | 154 | One sub-game's audit + settlement path. |
| `scripts/ref3_match/role_worker.py` | 153 | One role-worker process: control-frame loop plus play dispatch. |

Everything above 390 lines was already split into ≤150-line packages/mixins (the
reference-v3 wire, kit fixtures, the trainer, the gamelet, replay, the adaptive
protocol stack, and the match runner — `scripts/live_match_ref3.py` is now a
130-line facade over `scripts/ref3_match/`).

- ~~No committed GUI screenshot~~ CLOSED 2026-08-16: live belief-heatmap and replay Verified-OK screenshots captured during a real series live in `evidence/gui/` (see docs/GUI_PRD.md acceptance evidence).

The live GUI exists (`cop_worker/gui/app.py`, `cop_worker/gui/live_view_model.py`)
and is started per role worker when `[network] gui_cop_port` / `gui_thief_port`
is set (`scripts/ref3_match/gui_bridge.py`); with the keys absent — the default —
no GUI starts and play is byte-identical. `assets/screenshots/` carries match
visuals and a replay-verification capture, but **no browser screenshot of the
live GUI** is committed.

### D6: Duplicated modules across packages and repositories

The course mandates separate cop and thief repositories, so the domain layer is
vendored byte-identically in both (see `docs/ADR_001_shared_code_model.md`).
Inside this repository, `league_manager/` also carried copies of `cop_worker/`
modules; most are now import aliases of the canonical implementation
(`sys.modules[__name__] = sys.modules["cop_worker…"]` in `league_manager/gmail/*`,
`league_manager/protocol/*`), and where a real copy remains, mirrored `_lm` test
suites fail the build on drift. Full deduplication is deliberately deferred until
the league window closes (DESIGN AD-9).

## No longer deviations (removed from this list)

- **Trained RL checkpoint.** `models/MANIFEST.json` pins a promoted, SHA-stamped
  cop champion (`cop_chebyshev_champion.pt`), trained and evaluated on CPU
  (`docs/HARDWARE_STATEMENT.md`, `docs/RL_REPRODUCTION.md`).
- **Real Gmail send.** Every counted series in `results/counted_series.json`
  carries a real `report_message_id`; filed `.eml` copies are under
  `evidence/game_vs_*/`.
- **Group ID.** The group identifier is `vibecode` (`config/runtime.toml`
  `[identity] group_id`), used in every declaration and result artifact.
- **The legacy `agent/` tree.** Deleted; nothing in the repository imports it.
  Earlier entries here that pointed at `agent/rl/`, `agent/reports/`,
  `agent/gui/` or `agent/config_validator.py` described paths that no longer
  exist.
