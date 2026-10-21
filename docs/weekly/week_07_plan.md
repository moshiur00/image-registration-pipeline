# Week 7 Plan: Robustness Benchmarking, Calibration, and Failure Diagnosis

## Current state (2026-10-21)

- Week 6 registration methods, unified evaluation, and benchmark-runner contracts are frozen.
- UI v0.2 completed its manual acceptance checks, including normal, CT/MRI, one/two-candidate, failure, export, and changed-image-class invalidation scenarios. No UI changes are part of Week 7 Day 31.
- Day 31 is **complete and Windows validated**: 444 backend / 149 UI tests, 11/11 pilot attempts, all 11 skipped on resume.
- Day 32 is **complete and Windows validated**: 468 backend and 149 UI tests passed; the Windows dry run completed 49 attempts and resumed 49 with no reruns; the full development-only sweep completed all 963 attempts across 486 pairs. Offline geometric success was 840/963 (87.23%); all failures and CHECK records were retained. See `docs/daily/day_32_summary.md` and `reports/week07_day02_full_closure.json`.
- Day 33 is **complete, closed and Windows validated**: 504 backend tests passed (2 environmental symlink skips), 149 UI tests passed, 963 records processed, 13 figures, 12 gallery panels, and 6 optional CPU/sampled-RSS profiles. Uploaded Windows figures and profiler CSV were independently inspected and reconciled with the frozen Day 32 journal. Week 8 held-out evidence must not be used for calibration.
- Day 34 is **complete, closed and Windows validated**: 963 Day 32 records assessed offline using observable-only signals, a strict three-family agreement gate, internal seed-partition calibration, method-specific diagnostic bins and abstention. The provisional 2 px agreement candidate supports only 51/486 development pairs (435 abstain). This is NOT a production recommendation or calibrated confidence; see `docs/WEEK07_DAY34_OFFLINE_CALIBRATION.md`.
- Day 35 is **complete and Windows validated**: 552 backend tests passed with 3 expected skips, 149 UI tests passed. 88/88 combined-stress records preserved, 61 geometric successes, 11 execution failures; 0 executed/88 resumed. Frozen gate supported 2/40 pairs and abstained on 38, with no independent confidence claim. Week 7 development stage is closed, Week 8 remains not started.

## Day 31: Robustness matrix and resource pilot

Deliverables:

- A versioned 2D method snapshot in `configs/week07_day01_frozen_methods.yaml`.
- Severity grid and split declaration in `configs/week07_day01_robustness_grid.yaml`.
- Compatibility-aware development task enumerator in `src/image_registration/week7_robustness.py`.
- Design and small pilot runner in `scripts/week07_day01_robustness_design.py`.
- Reproducibility and correctness tests in `tests/test_week7_day31_robustness.py`.
- Design manifests under untracked `outputs/week07_day01_design/` and pilot runs under `outputs/week07_day01_pilot/`.
- Tracked design/pilot summary in `reports/week07_day01_robustness_design.json`.

Design choices:

- Reserve `moon.png` for Week 8 held-out evaluation. Day 31 pilot uses only `camera.png`.
- Source contents and frozen method snapshot are hashed. Incompatible method-model-modality cells are counted but not executed or mislabeled as algorithm failures.
- All Day 31 production registration calls use `RegistrationService` with reference status `UNAVAILABLE`. Ground truth is scoped to offline evaluation after execution.
- Each candidate receives a deterministic `BenchmarkTask` ID derived from the Week 6 runner. Only severity planning occurs now, not full severity execution.
- Run a tiny compatibility-aware pilot over translation, rigid, similarity, affine, and simulated multimodal affine cases. Keep failed and dependency-limited trials.

## Day 32: Controlled one-factor sweeps

Implement each planned severity using existing synthetic, degradation, modality and overlap utilities. For every model and modality, use matched geometric seeds across conditions where meaningful. Add tests proving the requested transform and the measured overlap. Execute the same pair with all compatible methods, retaining every failed attempt. Produce condition-by-severity TRE/success tables and ensure interrupted experiments resume.

## Day 33: Failure analysis and cost

Add failure taxonomy: insufficient texture, repetitive texture, inadequate overlap, initialization issues, optimizer divergence, mismatched transform model, intensity mismatch, and implausible transform. Record CPU/peak memory profiling on representative sizes, and generate automatically inspectable failure-case artifacts. Separate algorithm errors from ground-truth threshold failures.

## Day 34: Offline evidence calibration

Compare observable evidence against known synthetic geometric error. Examine transform agreement, method-family diversity, feature inlier/coverage evidence, ECC convergence, MI termination/stability, and valid overlap. Choose tentative gates and abstention rules from development evidence only, with uncertainty estimates where defensible. A single method or deterministic two-method medoid is not independent consensus evidence. Do not expose an unvalidated confidence percentage or a hard-coded ranking to UI v0.2.

## Day 35: Integrated validation and Week 7 closure

Run a small controlled combined-stress subset, regenerate plots and comparison matrices from machine-readable artifacts, manually review stratified failures, and document at least three recurring failure types and four condition-specific recommendations. Freeze a proposed calibration policy for evaluation, **not as a proven final policy**. Week 8 independently tests that policy against held-out cases.

## Acceptance criteria

- All planned mandatory conditions either executed or explicitly excluded with reason.
- Deterministic identities and resume result in no duplicate records.
- Failed and CHECK records remain in denominators and reports.
- TRE/parameter error only when valid reference exists; otherwise no geometric PASS.
- Fixed and moving transform convention remains Moving -> Fixed.
- Modality-stratified accuracy, success and runtime plots reproduce with a documented command.
- Ground-truth measurements are never passed into selection or recommendation.
- Frozen backend and UI regression baselines are preserved.

## Day 32 closure (2026-10-21)

The controlled severity sweep is closed with Windows validation (468 backend,
149 UI tests), a 49-attempt Windows dry run, and a full 963-attempt Windows run
across 486 compatible development pairs. All 963 records are unique; the
original 36 geometry-incompatible Day 31 pair scenarios remain documented
exclusions, not algorithm failures. Results: 934 Completed, 4 CHECK, 25 Failed;
840/963 (87.23%) meet the experimental 2-pixel TRE plus plausibility rule.
The CHECK records and wrong-geometry Completed results are retained for Day 33.
No recommendation thresholds or confidence claims are established here.
See `docs/daily/day_32_summary.md`, `docs/WEEK07_DAY32_CONTROLLED_SWEEPS.md`,
and `reports/week07_day02_full_closure.json`. UI v0.2 and algorithms are unchanged.

## Day 33 implementation handoff (2026-10-21)

Day 33 adds a frozen-record integrity validator, failure taxonomy and severity/runtime plots, reconstructed case gallery and a separately flagged optional CPU/sampled-RSS profiler. Local analysis covers all 963 recorded Day 32 attempts with no registration reruns, and finds 840 development-only geometric successes. Day 33 Windows regression and both analysis commands are validated. The Matplotlib 3.11 deprecation has been corrected. Windows-generated figures and profiling CSV have been independently inspected. Day 33 is formally closed; see `reports/week07_day03_closure.json`. See `docs/WEEK07_DAY33_FAILURE_ANALYSIS.md` and `docs/daily/day_33_summary.md`.

## Day 33 closure (2026-10-21)

Day 33 is **closed**: 504 backend tests passed and 2 symlink tests skipped on Windows; all 149 UI tests passed. The unchanged 963-attempt Day 32 journal yielded 840 development-only geometric successes and 123 geometric unsuccessful outcomes. All 13 charts, 12 reconstructed gallery images, and six CPU/sampled-process-RSS samples in the uploaded Windows export have been verified. Original Day 32 evidence is retained with matching SHA-256 checksums. The report `reports/week07_day03_closure.json` records evidence provenance and limitations. Next: Day 34 offline evidence calibration; final confidence/recommendations remain uncalibrated, and held-out Week 8 data remain untouched.

## Day 34 implementation handoff (2026-10-21)

Day 34's offline CLI produces a reproducible coarse threshold sensitivity grid, pair-level
abstention decisions, conditional geometric error audit, family-specific signal bins,
and three plots. It selects a *tentative* 2 px three-family agreement gate using only
development seeds 7 and 42, with seed 101 reserved as internal development audit.
Only 51 of 486 pairs earn tentative support (all 51 correct on synthetic development),
while 435 abstain; correlated evidence prevents claims of calibrated confidence.
No UI or algorithm changes, no new registration runs, no Week 8 held-out access.
Windows regression and original-artifact inspection passed; Day 34 is closed. See `reports/week07_day04_closure.json`.

## Day 34 closure (2026-10-21)

Day 34 is **closed** after Windows validation: 530 backend passed (2 environmental symlink skips), all 149 UI tests passed, and the offline CLI completed over 963 original Day 32 development attempts without registration reruns. Export inspection verified 486 unique pair decisions, 33/324 tuning and 18/162 internal-audit tentative supports (51/486 total; 435 abstained), three valid plots and matching four-source SHA-256 checksums.

Only monomodal affine pairs receive support under the exploratory three-method-family rule; all other model and simulated-multimodal pairs abstain. This is *not* a calibrated likelihood, a production selector or independent Week 8 validation. Source outputs and policy candidate remain frozen, offline, and non-deployed. Day 35 integrated validation has **not started**. See `reports/week07_day04_windows_validation.json` and `reports/week07_day04_closure.json`.

## Day 35 implementation handoff (2026-10-21)

Day 35 **implemented, Windows validation pending**: deterministic new-seed (202, 303) 40-pair, 88-compatible-attempt controlled combined-stress suite; read-only Day 32 comparisons, condition/method tables, four charts, frozen Day 34 gate evaluated without retuning, 10-panel reconstructed review gallery and manual-review queue, four recurring failure modes and six condition-specific handling recommendations. The development policy remains offline. Local SimpleITK absence affected 24 MI trials; local journal is intentionally **not included** in the Windows handoff ZIP. Do not close Week 7 before Windows run and evidence review. Details: `docs/WEEK07_DAY35_INTEGRATED_VALIDATION.md`, `docs/daily/day_35_summary.md`, and `reports/week07_day05_week08_handoff.json`.

## Day 35 and Week 7 closure (2026-10-21)

All Day 35 acceptance checks passed based on uploaded Windows evidence and offline inspection. Twenty-seven of 88 attempts were geometrically unsuccessful (16 incorrect estimated geometries and 11 execution failures). Correspondence failures were retained. Four figures and ten reconstructed failure gallery images were reviewed visually by the assistant; an independent human signoff was not represented as completed.

The unchanged, experimental Day 34 policy supported just 2/40 new development pairs with two correct synthetic selections, while abstaining 38/40. It was not retrained or deployed. Source-hash reconciliation used the preserved complete evidence from Days 32-34, as the selective Day 35 ZIP does not carry them. No Week 8 heldout pixels or labels were accessed. `reports/week07_week_closure.json` is the authoritative Week 7 closure record.

**Next:** Week 8 independent held-out validation before any calibration/confidence, universal ranking, or production automatic decision claims.
