# Pre-Week 8 Stage B: UI acceptance support

Status: **PASSED; MANUALLY ACCEPTED AT 5/5 SCENARIOS + 5/5 SUPPLEMENTAL; UI v0.2 FROZEN**.

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

The QA command initially returned `PENDING_MANUAL_QA`. Named reviewer Md
Moshiur Rahman subsequently completed and attested all five scenarios and all
five supplemental checks on Windows. The status command now returns
`MANUALLY_ACCEPTED`.

The earlier computer-use runtime failed during initialization before any
application interaction. It was not substituted for human review. The later
walkthrough was performed by the named reviewer and backed by private hashed
screenshots and ZIP evidence under ignored `ui/runtime/`.

## Final Stage B validation (14 November 2026)

The post-hardening regression is green: 702 backend tests passed with 3
expected skips and 179 UI tests passed. The hardened Stage B focused suite is
30/30 passed, and all 66 preflight tests pass. Development preflight is 18 PASS
/ 1 BLOCK; the sole development blocker remains independent Week 8 source
enrollment. Strict preflight remains blocked on expected Phase 5+ release,
source, dependency/environment, signoff, and restoration prerequisites.

Human status is 5/5 scenarios plus 5/5 supplemental checks. The sanitized
tracked report is `reports/pre_week08_stage_b_validation.json`, which records
`formal_ui_v02_frozen=true`. UI v0.2 is formally frozen; this does not approve
Week 8 execution or claim scientific calibration.

Optional scope is now explicit: Stage C Research Evidence, interactive RIRE
expansion, and the dormant recommendation display path are all DEFERRED.
