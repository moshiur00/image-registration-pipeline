# Pre-Week 8 Stage B: UI acceptance support

Status: **IMPLEMENTED, LOCAL AUTOMATED TESTS PASSED, MANUAL WINDOWS WALKTHROUGH PENDING**.

## Scope

- Implemented deterministic QA PNG generator and operator-attested checklist for the existing Automatic Comparison UI.
- Added 5 concrete UI scenarios: simulated multimodal compatibility, single-candidate agreement limits, CHECK/Failed preservation, stale result/export invalidation, and archive provenance.
- Added automated checks for fixture reproducibility, raw-byte hashes, manual-result status, expected single-candidate method filtering, and stale UI state clearing.
- Generated fixtures intentionally reuse a development source. They are excluded from independent Week 8 held-out evaluation.

## Unchanged

All registration algorithms, original UI production code, Day 34 policy, Week 7 benchmark artifacts, and frozen baseline hashes remain unchanged. No final recommendations or confidence scores have been enabled.

## Acceptance gate

The QA command initially returns PENDING_MANUAL_QA (0/5 manual cases passed). A manual operator must complete the five scenarios on Windows, then supply observed results. Do not label UI v0.2 frozen until those results are reviewed.

## Current checkpoint validation (3 November 2026)

The current Windows regression is green: 575 backend tests passed with 2
expected skips, and 166 UI tests passed. This supersedes the pre-Stage B
149-test UI baseline as the current automated record. It does not satisfy the
operator-attested acceptance gate: manual status remains 0/5 and UI v0.2
remains a release candidate, not frozen.
