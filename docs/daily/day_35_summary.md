# Day 35: Integrated validation and Week 7 handoff

**Status: complete and Windows validated; Day 35 and Week 7 development stage closed (2026-10-21).**

- Added the deterministic 40-pair, 88-method-attempt two-factor development suite using new seeds 202/303, with support-mask and Moving -> Fixed reference preflight.
- Added the read-only Day 32 evidence reconciliation, split-preserving cross-study comparison, per-condition and per-method tables, four generated charts, manual-review candidates and a 10-panel reconstructed gallery.
- Added six condition-specific cautious guidance entries and four recurring Day 32 failure types, with input count and provenance. They are not general-purpose automatic method rankings.
- Applied the **unchanged, non-deployed** Day 34 exploratory gate offline after candidate execution. Ground truth never enters the service or candidate selection. Day 34 calibration/audit data and the Week 8 holdout were not accessed for retuning.
- Added standalone reproducibility guidance and Week 8 frozen-policy handoff report.
- Local dry execution: 88/88 attempts recorded and all 88 skipped on repeat. Local environment lacks SimpleITK; 24 MI attempts are dependency failures. Its preview must not be shipped as a Windows resumable journal or used to judge final results. Windows test counts and full execution evidence are pending.
- Backend and frozen UI code are unchanged. Day 35 is not formally closed and Week 7 is not declared complete.

See `docs/WEEK07_DAY35_INTEGRATED_VALIDATION.md`.

## Windows final validation and Week 7 closure (2026-10-21)

- Backend: 552 passed, 3 skipped, no failures. UI: 149 passed. The optional Day 35 evidence test was skipped in the original selective export, but the complete closure archive now contains all baseline evidence.
- Windows combined suite: 40 development pairs, 88 unique attempts; 77 Completed, 11 Failed, 0 CHECK and 0 validation errors. Offline geometry: 61/88 (69.32%) correct, including execution failures in the denominator. Of the 77 completed attempts, 16 returned incorrect geometry.
- Execution failures: 9 insufficient filtered feature matches and 2 insufficient RANSAC inliers. The second run resumed 88 existing attempts and executed 0.
- Frozen Day 34 experimental gate: 2/40 tentatively supported, 38/40 abstained; both selected transforms correct only within this small synthetic sample. Wilson 95% lower bound is approximately 0.342 and does not establish calibrated confidence.
- Four charts and ten reconstructed failure panels inspected. Separate assistant visual-review notes are recorded without claiming independent human signoff. Six conservative condition-specific guidance entries and four Day 32 recurring failure categories are retained.
- Original Day 32 evidence and frozen Day 34 policy hashes reconcile with the older validated archive; 32-34 outputs were merged into this complete closure package because the selective Day 35 ZIP omitted those directories. Week 8 held-out pixels remain untouched, and registration algorithms, frozen UI and gate are unchanged.
- Archived Day 35 output manifests still contain their original before-acceptance status strings; this is intentional immutable provenance. The tracked closure reports supersede that status for project management, not for altering benchmark evidence.

See `reports/week07_day05_closure.json`, `reports/week07_week_closure.json`, `reports/week07_day05_gallery_visual_review.json` and `reports/week07_day05_windows_validation.json`.
