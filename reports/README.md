# Report Snapshots

This directory keeps compact, machine-readable progress summaries with the source repository so later technical-report generation does not depend only on local `outputs/` folders.

The project uses two result layers:

1. `outputs/` contains complete run artifacts such as CSV/JSON tables, resolved configurations, plots, images, logs, and per-case diagnostics. These files can be large and are intentionally excluded from Git and lightweight sharing archives.
2. `reports/` contains compact JSON snapshots of validated milestones and experiment summaries. These files are small and are tracked with the project.

Narrative context is stored separately in `docs/daily/` and `docs/weekly/`.

For future report generation, use all three sources when available:

- `reports/` for compact quantitative summaries;
- `docs/daily/` and `docs/weekly/` for implementation decisions and interpretation;
- the local `outputs/` directory for full tables, figures, and case-level evidence.

Week 3 experiment scripts write or refresh their compact report snapshot automatically after a successful run.

## Week 3 baseline snapshots

Week 3 stores one compact JSON snapshot for each experimental day. Day 5 also writes an integrated baseline snapshot containing method-level, condition-level, and motion-model summaries. The raw CSV/JSON tables and figures remain under `outputs/`, while the compact snapshot stays tracked with the repository.
## Consolidated findings

`findings_days_01_15.json` preserves the main measured evidence, observations, interpretations, limitations, and source-record paths from Days 1 to 15. It is intended as a compact input for later technical-report writing.

`week03_summary.json` provides a compact Week 3 milestone summary and links the five detailed Week 3 experiment snapshots.

Future experimental days should follow `docs/EXPERIMENT_REPORTING_STANDARD.md` so quantitative evidence and narrative observations are stored together.


## Week 4 feature-based snapshots

`week04_day01_orb_features.json` stores Day 16 ORB detection and descriptor evidence, including per-case feature counts, descriptor counts, response statistics, spatial coverage, runtime, observations, interpretation, limitations, and target-machine validation status.

`week04_day02_orb_matching.json` stores Day 17 descriptor-matching evidence for KNN ratio filtering and cross-check matching. It includes accepted-match counts, Hamming-distance summaries, correspondence coverage, the ratio-threshold sweep, observations, limitations, and target-validation status.

`week04_day03_ransac_similarity.json` stores the validated Day 18 similarity-model evidence, including RANSAC inlier diagnostics, reprojection residuals, ground-truth transform errors, the controlled correspondence-outlier experiment, and target Windows validation.

`week04_day04_ransac_affine_robustness.json` stores the validated Day 19 affine-model evidence, including correspondence degeneracy checks, transform plausibility diagnostics, texture stratification, similarity-versus-affine comparison, the matching/RANSAC threshold sweep, and target Windows validation.

`week04_day05_integrated_feature_baseline.json` stores the Day 20 integrated monomodal comparison across frequency-, intensity-, and feature-based methods. It keeps translation, rigid, and affine shared-case groups separate, preserves feature-specific diagnostic failures, and records target-validation status.

Week 4 snapshots follow `docs/EXPERIMENT_REPORTING_STANDARD.md`. Days 16 through 20 include completed target Windows validation. `week04_summary.json` provides the compact completed-week milestone summary.

`findings_week04.json` is the consolidated Week 4 findings registry. Each completed experimental day should append its measured evidence, observations, interpretation, limitations, decision, and source-record paths there.

## Week 4 optional SIFT extension

`week04_sift_extension_summary.json` records the three-stage optional SIFT comparison started after completion of the core Week 4 ORB + RANSAC work.

`week04_sift_stage01_features_matching.json` stores Stage 1 SIFT detection, 128-dimensional float descriptors, L2 KNN ratio matching, spatial coverage, runtime, ratio-threshold sweep, observations, interpretation, limitations, and target-validation status.

The extension is intentionally kept separate from the five completed Week 4 working days. Stage 1 is complete and validated on the target Windows environment with 327 tests passing in 9.44s. `week04_sift_stage02_ransac.json` stores the completed Stage 2 SIFT + shared RANSAC evidence. Target Windows validation on 2026-09-29 recorded 329 tests passing in 8.73s and 12 / 13 cases inside the configured geometric tolerances. `week04_orb_vs_sift_comparison.json` stores the frozen Stage 3 paired comparison. Target Windows validation completed with 333 tests passing in 3.57s, and SIFT was retained as an optional complement.

## Week 5 snapshots

`week05_day01_mi_rigid.json` stores the completed Day 21 rigid Mutual Information target evidence. The validated Windows run recorded 340 tests passing in 3.73s, 6 / 6 method executions, 4 / 6 registrations inside the configured geometric tolerance, and preserved the histogram-remap and edge-emphasized CHECK cases.

`week05_day02_mi_rigid_study.json` stores the completed Day 22 validation study. Target Windows validation recorded 347 tests passing in 8.65s. The frozen confirmation reached 5 / 5 cases within tolerance with median TRE 0.0173 px, and the selected rigid MI configuration uses identity initialization, 32 histogram bins, full metric sampling, and Gaussian smoothing with sigma 1.0.

`week05_day03_mi_affine_multiresolution.json` stores the completed Day 23 affine MI comparison. Target Windows validation recorded 352 tests passing in 8.68s. Single-resolution and multiresolution affine MI each reached 5 / 7 cases within tolerance; multiresolution reduced median TRE but did not add any within-tolerance cases.

`week05_day04_rire_physical_registration.json` stores the completed Day 24 real RIRE CT/MR-T1 technical evidence. Target Windows validation recorded 358 tests passing in 4.59s. Both configured rigid 3D initialization variants passed the technical checks and preserved metadata. TRE, Dice, and anatomical correctness are not reported because verified landmarks or masks are not integrated.

`week05_day05_integrated_benchmark.json` stores the frozen Day 25 final synthetic benchmark and Week 5 closure evidence. Target Windows validation recorded 364 tests passing in 4.56s. The benchmark contains 13 final cases and 26 registrations. Mutual Information reached 11 / 13 cases within tolerance and ECC reached 7 / 13; all failure and CHECK records remain retained.

`week05_summary.json` is the compact completed-week index linking Days 21 through 25, their target validations, frozen configuration decisions, and the next Week 6 action.

`findings_week05.json` consolidates the validated Week 5 measured evidence, observations, interpretations, limitations, decisions, and source-record paths for later technical-report generation.

Full figures, CSV tables, resolved configurations, and per-case diagnostics remain under local `outputs/` and are intentionally excluded from Git and lightweight shared ZIPs.
