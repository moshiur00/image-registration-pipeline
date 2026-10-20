# Day 26: Unified Evaluation Semantics and Result Contract

## Status

Complete. Target Windows validation passed with 376 backend tests in 6.28s and 64 UI tests in 5.36s. The Day 26 contract script completed successfully with 25 metric definitions.

## Purpose

Day 26 starts Week 6 by defining one method-independent evaluation contract before implementing the full metric suite or automatic multi-method runner. The goal is to make Phase Correlation, ECC, ORB + RANSAC, SIFT + RANSAC, and Mutual Information comparable without hiding their method-specific diagnostics or confusing optimizer completion with correctness.

## Setup

The validated Weeks 1 to 5 algorithms and frozen configurations remain unchanged. Day 26 adds a new generic evaluation-contract module, configuration, tests, documentation, and a compact report snapshot.

## Variable changed

The project now has an explicit shared vocabulary for:

- metric role and units;
- reference-evidence availability;
- valid-overlap requirements;
- execution status;
- geometric PASS/CHECK eligibility;
- stage-level timings;
- a common method-independent candidate record supporting 2D and 3D homogeneous transforms.

## Factors kept fixed

- Moving -> Fixed transform convention;
- `(x, y)` point coordinate order for 2D and `(x, y, z)` for 3D;
- all registration algorithms;
- all Weeks 1 to 5 method settings and thresholds;
- existing reports and validated experiment evidence.

## Metrics and policy

The contract distinguishes geometric error, anatomical overlap, descriptive similarity, valid overlap, and runtime. It explicitly records whether a metric requires an exact transform, geometric reference, reference mask, physical spacing, or valid overlap.

The contract prevents unknown image pairs from reporting TRE, transform-parameter error, Dice without masks, or a geometric PASS/CHECK state. NCC, SSIM, MAE, MSE, and evaluation MI remain descriptive evidence only.

## Results

The Day 26 script validates the metric catalog and produces scenario-specific metric availability for:

- known synthetic ground truth;
- unknown uploaded images;
- mask-based reference data;
- physical-space known transforms.

The script also writes a local evaluation-contract JSON and metric-catalog CSV under `outputs/week06_day01_unified_evaluation/`, plus the tracked compact report `reports/week06_day01_unified_evaluation.json`.

## Observations

A common schema can represent all current methods without comparing raw ECC, MI, phase-response, or RANSAC values directly. Method-specific diagnostics remain separate from comparable evaluation metrics.

## Interpretation

This contract is the prerequisite for both reproducible benchmarking and later automatic registration. Automatic comparison is only defensible if every candidate uses the same transform convention, reference policy, overlap rule, and evaluation semantics.

## Failure cases

Day 26 treats the following as explicit contract errors:

- empty valid overlap;
- unavailable ground-truth metric requested for an unknown pair;
- geometric PASS/CHECK requested without geometric reference evidence;
- failed execution record without a failure reason;
- invalid transform shape or non-finite metric values.

## Limitations

Day 26 defines metric semantics but does not yet implement all Week 6 metric calculations. It does not rank methods, calibrate confidence, or change any registration method.

## Decision and next experiment

The target Windows evidence was reviewed and the Day 26 contract is frozen. Day 27 now implements and independently tests model-aware parameter error, TRE summaries, Dice, overlap-aware descriptive metrics, and evaluation Mutual Information.
