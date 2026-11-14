# Pre-Week 8 Stage B: UI acceptance support

Status: **ATTESTATION V2 IMPLEMENTED; HUMAN WINDOWS WALKTHROUGH PENDING AT 0/5 SCENARIOS + 0/5 SUPPLEMENTAL**.

## Scope

- Implemented deterministic QA PNG generator and operator-attested checklist for the existing Automatic Comparison UI.
- Added 5 concrete UI scenarios: simulated multimodal compatibility, single-candidate agreement limits, CHECK/Failed preservation, stale result/export invalidation, and archive provenance.
- Added automated checks for fixture reproducibility, raw-byte hashes, manual-result status, expected single-candidate method filtering, and stale UI state clearing.
- Hardened the local record and CLI so a scenario cannot be accepted without a
  named human Windows reviewer, environment, exact tested commit, concrete
  observation, runtime-local screenshot/ZIP references, and reverified hashes.
- Required separate evidence-backed human records for the normal monomodal,
  unknown-upload claim-suppression, RIRE caveat, inspection-label, and
  no-frozen-write checks. Records are bound to the exact fixture manifest and a
  real ancestor Git commit.
- Added a sanitized tracked-report builder. It cannot freeze UI v0.2 unless all
  five scenario records and all five supplemental human records pass and both
  full suites report zero failures.
- Generated fixtures intentionally reuse a development source. They are excluded from independent Week 8 held-out evaluation.

## Unchanged

All registration algorithms, original UI production code, Day 34 policy, Week 7 benchmark artifacts, and frozen baseline hashes remain unchanged. No final recommendations or confidence scores have been enabled.

## Acceptance gate

The QA command initially returns PENDING_MANUAL_QA (0/5 manual cases passed). A manual operator must complete the five scenarios on Windows, then supply observed results. Do not label UI v0.2 frozen until those results are reviewed.

The current session's Windows computer-use runtime failed during initialization
before any application interaction. No automated observation was relabeled as a
human assertion, and no manual acceptance record or tracked freeze report was
generated.

## Current checkpoint validation (13 November 2026)

The post-hardening regression is green: 702 backend tests passed with 3
expected skips and 179 UI tests passed. The hardened Stage B focused suite is
30/30 passed, and all 66 preflight tests pass. Development preflight is 18 PASS
/ 1 BLOCK; strict preflight is 18 PASS / 11 BLOCK. Automated success does not
satisfy the human gate: status remains 0/5 scenarios plus 0/5 supplemental
checks, and UI v0.2 remains a release candidate, not frozen.

Optional scope is now explicit: Stage C Research Evidence, interactive RIRE
expansion, and the dormant recommendation display path are all DEFERRED.
