# SIFT Extension Stage 2: RANSAC Geometry

## Status

Complete and validated on the target Windows environment on 2026-09-29.

## Purpose

Test whether the SIFT correspondences retained in Stage 1 recover correct Moving -> Fixed geometry when passed to the existing similarity and affine RANSAC estimators.

## Setup

Stage 2 keeps the validated Stage 1 SIFT front-end fixed:

- maximum SIFT features: 800;
- 128-dimensional float descriptors;
- L2 KNN matching;
- ratio threshold: 0.75;
- minimum filtered matches: 8.

The RANSAC estimators are the same shared modules already used by the ORB pipeline. Stage 2 does not create SIFT-specific RANSAC algorithms.

The controlled set contains 13 cases:

- 7 similarity-model cases;
- 4 ordinary affine cases;
- 2 affine failure probes for low texture and repeated structure.

The blur and partial-overlap cases reuse controlled conditions already used in the Week 4 feature experiments. The affine transform parameters and failure probes also reuse the established Week 4 configurations.

## Metrics and thresholds

Stored diagnostics include filtered matches, correspondence coverage, RANSAC inliers and outliers, inlier ratio, reprojection residuals, estimated transform, TRE, parameter errors, runtime, execution success, geometric tolerance status, and explicit failure reason.

Similarity development tolerances:

- TRE: 2.0 px;
- centered translation error: 3.0 px;
- rotation error: 1.0 degree;
- scale error: 0.03.

Affine development tolerances:

- TRE: 3.0 px;
- centered translation error: 4.0 px;
- affine linear-component error: 0.05.

These remain development thresholds rather than frozen final-benchmark criteria.

## Target Windows validation

The full test suite completed successfully:

- `329 passed in 8.73s`;
- 0 failures.

The Stage 2 experiment produced:

- matching success: 12 / 13;
- RANSAC execution success: 12 / 13;
- inside configured geometric tolerances: 12 / 13.

Similarity cases:

- 7 / 7 RANSAC successes;
- 7 / 7 inside tolerance;
- median TRE: 0.061 px;
- maximum TRE: 0.236 px;
- mean inlier ratio: 0.947;
- mean total runtime: 91.734 ms.

Affine cases including the two failure probes:

- 5 / 6 RANSAC successes;
- 5 / 6 inside tolerance;
- median numeric TRE: 0.116 px;
- maximum numeric TRE: 1.247 px;
- mean inlier ratio across cases with returned ratios: 0.948;
- mean total runtime: 68.893 ms.

Selected target Windows cases:

| Case | Model | Filtered matches | RANSAC inliers | TRE (px) | Result |
|---|---|---:|---:|---:|---|
| camera_translation | Similarity | 671 | 668 | 0.008 | Pass |
| camera_rotation | Similarity | 437 | 415 | 0.139 | Pass |
| camera_similarity_small | Similarity | 451 | 433 | 0.061 | Pass |
| camera_similarity_medium | Similarity | 397 | 382 | 0.126 | Pass |
| camera_scale | Similarity | 393 | 383 | 0.058 | Pass |
| camera_blur | Similarity | 47 | 38 | 0.236 | Pass |
| camera_partial_overlap | Similarity | 424 | 416 | 0.005 | Pass |
| camera_affine_mild | Affine | 430 | 422 | 0.058 | Pass |
| camera_affine_medium | Affine | 355 | 337 | 0.153 | Pass |
| coins_affine | Affine | 324 | 306 | 0.116 | Pass |
| moon_affine | Affine | 61 | 60 | 0.104 | Pass |
| low_texture_affine | Affine | 17 | 15 | 1.247 | Pass |
| repeated_pattern_affine | Affine | 0 | 0 | n/a | Expected diagnostic failure |

## Observations

SIFT produced geometrically consistent estimates on every ordinary similarity and affine case in the target Windows run. Blur strongly reduced the number of retained correspondences, but the remaining matches were sufficient for the configured similarity RANSAC case.

The low-texture probe returned only 17 filtered matches but still produced a geometrically acceptable affine estimate under the current thresholds. This is case-specific evidence and does not establish general low-texture reliability.

The repeated-pattern probe failed before RANSAC because no matches survived the ratio filter. This failure is preserved because repetitive structure and low texture are different failure mechanisms.

## Interpretation

Stage 2 confirms that the same shared RANSAC implementations can consume SIFT correspondences and recover correct geometry under the selected controlled cases. Descriptor filtering success, RANSAC execution success, and geometric correctness remain separate result fields.

Stage 2 is not the final ORB versus SIFT comparison. The next stage uses the same image pairs, ground truth, transform model, RANSAC settings, evaluation points, success criteria, and result schema for both feature front-ends.

## Limitations

- The controlled subset is intentionally small.
- Runtime depends on the target machine, OpenCV build, and thread scheduling.
- Stage 2 evaluates SIFT only and therefore cannot determine the final role of SIFT relative to ORB.

## Decision

Stage 2 is complete. Proceed with the frozen Stage 3 ORB versus SIFT comparison without retuning the validated Stage 2 thresholds.
