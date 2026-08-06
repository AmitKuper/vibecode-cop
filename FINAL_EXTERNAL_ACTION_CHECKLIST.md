# Final external action checklist

Evidence date: 2026-08-06. Localhost, fixtures, fake Gmail, illustrative screenshots,
generated identities, and local-only tags are not acceptable evidence.

| Rule(s) | Required genuine action | Required evidence | Status |
|---|---|---|---|
| 10, 31 | Run counted play over a public tunnel against at least two distinct course groups, once per stable opponent. | Public URLs, peer identities, timestamps, signed agreements, both process logs, reciprocal ledgers. | EXTERNAL_PENDING |
| 32 | Authorize each role independently with send-only Gmail OAuth and send its signed JSON result. | Two provider-returned message IDs and matching canonical JSON hashes. | EXTERNAL_PENDING |
| 8, 20, 43 | Capture the real final Live GUI local-belief view and Replay `VERIFIED OK`, and place required evidence in the official unchanged-layout PDF. | Original screenshots and final PDF SHA-256. | EXTERNAL_PENDING |
| 44 | Every member submits the official PDF separately in Moodle. | Individual Moodle receipts/screenshots. | EXTERNAL_PENDING |
| 45 | Supply the team's real unique eight-character ID. | Course-issued identity used consistently in both role environments and evidence. | EXTERNAL_PENDING |
| 41 | After the exact-current-SHA verifier passes, create and push immutable annotated release tags and verify remote resolution. | Remote URLs, tag objects, and `git ls-remote --tags` output. | EXTERNAL_PENDING |

Code/evidence basis before final release-document commit:

- Cop: `dedaaf147989d1b63f4d4536330bf70335df4630`
- Thief: `55d45fcd4010884b08c64380fe03c6cd39062266`

Do not mark a row PASS until its external artifact is independently checkable.
