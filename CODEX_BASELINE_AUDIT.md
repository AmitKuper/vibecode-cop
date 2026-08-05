# v11 Independent Baseline Audit

Cross-repository evidence date: 2026-08-06. Cop started clean at
`115c20e60d3a318b117136b30661e3ea3b788e35`; thief started clean at
`7ba1ad7fd42eb70cb7cf0690c512a23ca5dc3bf4`.

Fresh gates passed in both repositories: `uv sync --frozen`, lock check,
production CLI, full no-skip pytest, branch coverage >=85%, Ruff lint/format,
model checksum/inference, exact tournament reproduction, hostile focused tests,
and a real isolated six-gamelet process series
`series_20260806_005228_14283ab9`. Cop had 1,509 tests and 85.9867% branch
coverage; thief had 1,384 and 85.5100%. Cop tournament strength was 89.00%
overall / 79.03% worst-family; thief was 76.11% / 34.44%.

The legacy verifier's 11 PASS result is valid only for its own gates. Direct v11
inspection found binding failures in Appendix-E rules 6, 7, 17, 19, 20, 21,
23, and 36. Rules 10, 31, 32, 41, 43, 44, and 45 remain genuinely
`EXTERNAL_PENDING`. Initial matrix totals: 40 PASS, 8 FAIL, 7 external pending.

Independent scores: project requirements 83/100, agent strength 82/100,
unknown-MCP adaptation 55/100, overall 73/100. The main defects are
gamelet-1-default commitment binding, incomplete/extent-inferred audit,
unanchored non-reconstructive replay, bypassed canonical outcome/config, split
and double scent, fail-open heartbeat publication, weak MCP response semantics
and conformance, no real alternate-server six-gamelet proof, and thief
worst-family weakness. Full evidence and interpretation are in
`docs/CODEX_100_EXECPLAN.md` and `docs/REQUIREMENTS_TRACEABILITY.md`.

No public-tunnel, other-team, real-Gmail, group-ID, screenshot, Moodle, or final
tag evidence is claimed.
