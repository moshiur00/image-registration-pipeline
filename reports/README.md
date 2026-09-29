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
