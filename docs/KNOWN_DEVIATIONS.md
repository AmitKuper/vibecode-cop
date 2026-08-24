# Known Deviations from the Original Specification

Every entry below is a deviation that is **still true today** (2026-08-15), with
the file or artifact that proves it. Items that were once listed here and have
since become false were removed rather than reworded; see "No longer deviations"
at the end for what changed.

## Active deviations

### D1: Network-ingress implementation choice — public reachability without a tunnel

The book describes tunnelling tools (ngrok/Cloudflare, §2.4) whose stated purpose
is NAT traversal for hosts that cannot be reached directly; the binding source
(Appendix F) mandates no specific ingress tool. We expose the two role endpoints
on a router-forwarded **static public IP** (cop 61224 / thief 61223), so the
requirement's purpose — public Internet reachability — is met without
the tool. This was demonstrated across the internet in ten counted cross-team
series against ten distinct opponents (`results/counted_series.json`). The tunnel
path itself is implemented AND exercised with our own door behind the tunnel: a
full six-window bench series settled 6/6 `Verified OK` on 2026-08-24 with our
cop door served through a live ngrok tunnel (traffic confirmed via ngrok's
inspection API; details in `docs/NGROK_INGRESS.md`), on top of the 2026-08-14
live agent verification and counted game 9 (vm__fabi, won 90-30) dialing the
opponent's ngrok tunnel. Static ingress is itself a configured capability, not
a shortcut — it required router administration (two port-forwarding rules,
public 61224/61223 → the match host) — and it was chosen because it serves BOTH
doors always-on at no fee, while the free ngrok tier tunnels only one. ngrok remains
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

### D4 — RESOLVED 2026-08-24: 150-line module limit now strictly met

Every Python file in the repository is at or under 150 lines and
`scripts/check_file_size.py` enforces the limit **strictly — the former
per-file allowance ledger was emptied and removed**. The 22 remaining
oversized modules were refactored by cohesive extraction (never line-count
tricks): the transition core's four identical result-construction blocks
became `transition_result._finish` (mirrored in the thief repo; kit vectors
and cross-repo conformance suites pin behavior), the wire session's tool
registration moved to `session_tools.py`, the match lifecycle's
identity/inbound/settlement helpers into `setup_identity.py` /
`turns_inbound.py` / `settle_disputed.py` / `artifacts_profile.py` /
`worker_strays.py`, the cop chain into `search_policy_cop.py` +
`hunt_walls.py`, GUI page templates' script halves into `*_js.py` modules,
and lab/test scenarios into focused modules. Full suites, golden corpora,
lab matrices, and a six-window split rehearsal all reproduce their
pre-refactor results.

Everything above 390 lines was already split into ≤150-line packages/mixins (the
reference-v3 wire, kit fixtures, the trainer, the gamelet, replay, the adaptive
protocol stack, and the match runner — `scripts/live_match_ref3.py` is now a
130-line facade over `scripts/ref3_match/`).

- ~~No committed GUI screenshot~~ CLOSED 2026-08-16: live belief-heatmap and replay Verified-OK screenshots captured during a real series live in `evidence/gui/` (see docs/GUI_PRD.md acceptance evidence).

The live GUI exists (`cop_worker/gui/app.py`, `cop_worker/gui/live_view_model.py`)
and is started per role worker when `[network] gui_cop_port` / `gui_thief_port`
is set (`scripts/ref3_match/gui_bridge.py`); with the keys absent — the default —
no GUI starts and play is byte-identical. Browser screenshots of the live GUI
(belief heatmaps for both roles) and the replay `Verified OK` view are committed
in `evidence/gui/`; `assets/screenshots/` additionally carries match visuals.

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
