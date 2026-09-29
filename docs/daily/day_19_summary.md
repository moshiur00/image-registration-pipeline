# Day 19 Summary: Affine RANSAC and Robustness Diagnostics

## Status

Complete and validated on the target Windows environment.

## Purpose

Extend ORB + RANSAC from similarity estimation to affine estimation and add explicit checks for unstable correspondence geometry, implausible transforms, texture level, and threshold sensitivity.

## Setup

The experiment uses the existing ORB detector and KNN ratio-filtered Hamming correspondences. Affine RANSAC estimates the Moving -> Fixed transform. The same accepted correspondences are also passed to the existing similarity RANSAC estimator for a controlled model comparison.

Nine controlled cases are included:

- one true similarity reference case;
- several textured affine cases;
- affine motion with occlusion;
- affine motion with restricted field of view;
- a naturally lower-texture moon case;
- a strongly blurred low-texture case;
- a procedural repeated-pattern ambiguity case.

## Variables changed

The main Day 19 experiment changes:

- motion model from similarity to general affine;
- texture level;
- occlusion and field-of-view condition;
- ORB ratio threshold in the sweep;
- RANSAC reprojection threshold in the sweep.

## Factors kept fixed

The target run keeps the core ORB settings, Hamming descriptor type, Moving -> Fixed convention, validation metrics, source preparation rules, and random seed fixed unless the sweep explicitly changes a threshold.

## Metrics and thresholds

Primary measurements:

- TRE;
- affine linear-component error;
- centered translation error;
- accepted matches;
- RANSAC inlier count and inlier ratio;
- reprojection residuals;
- correspondence grid coverage;
- correspondence linearity ratio;
- transform plausibility diagnostics;
- normalized gradient energy;
- keypoint density;
- runtime;
- explicit failure reason.

Development correctness thresholds are stored in `configs/week04_day04_ransac_affine_robustness.yaml`. They remain working thresholds and are not final benchmark settings.

## Target Windows validation

The full repository test suite completed successfully:

- 304 / 304 tests passed;
- 0 failed;
- 0 skipped;
- runtime: 4.27 seconds.

The Day 19 target experiment produced:

- 9 controlled image cases;
- 7 / 9 successful affine RANSAC estimates;
- 7 / 9 results within the configured geometric tolerances;
- mean successful-case inlier ratio: 0.871;
- median affine TRE: 0.523 px;
- maximum returned TRE: 15.599 px;
- 3 / 3 controlled degeneracy and plausibility probes produced their expected failure labels;
- 120 threshold-sweep combinations were recorded.

Representative target-run cases:

| Case | Matches | Affine inliers | Affine TRE | Similarity TRE | Result |
|---|---:|---:|---:|---:|---|
| camera_similarity_reference | 386 | 310 | 0.661 px | 0.657 px | pass |
| camera_affine_mild | 489 | 465 | 0.111 px | 11.910 px | pass |
| camera_affine_medium | 344 | 280 | 0.706 px | 25.635 px | pass |
| camera_affine_occlusion | 145 | 127 | 0.544 px | 18.428 px | pass |
| camera_affine_partial_overlap | 400 | 363 | 0.364 px | 16.389 px | pass |
| coins_affine | 278 | 223 | 0.503 px | 9.294 px | pass |
| moon_affine | 224 | 212 | 0.200 px | 17.683 px | pass |
| low_texture_affine | 8 | 6 | 15.599 px | 15.987 px | rejected |
| repeated_pattern_affine | 0 | 0 | n/a | n/a | matching failure |

## Observations

1. The smallest affine TRE occurred in `camera_affine_mild` at 0.111 px.
2. The largest returned TRE occurred in `low_texture_affine` at 15.599 px. The result was rejected because only six RANSAC inliers remained.
3. The true similarity reference produced almost identical TRE for similarity and affine RANSAC, 0.657 px and 0.661 px respectively. Extra affine flexibility did not improve this case.
4. On all seven true-affine cases where both models returned a numeric TRE, affine RANSAC produced the lower TRE. The repeated-pattern case produced no filtered matches, so no model comparison was possible there.
5. Occlusion reduced accepted matches to 145, but 127 remained geometrically consistent and the affine estimate achieved 0.544 px TRE.
6. Restricted field of view retained 400 accepted matches and 363 RANSAC inliers, with 0.364 px TRE.
7. The repeated-pattern case had no matches after the default descriptor ratio filter. Strong local gradients therefore did not guarantee distinctive correspondences.
8. The threshold sweep produced 80 within-tolerance results across 120 case and threshold combinations. Changing thresholds did not repair cases where the underlying correspondence information was inadequate.

## Degeneracy and plausibility probes

Three direct probes verify that failure rules are active:

- collinear correspondences -> `degenerate_correspondences_collinear`;
- clustered correspondences -> `poor_spatial_coverage`;
- excessive affine scale -> `implausible_principal_scale`.

All three produced the intended failure record on the target experiment path.

## Interpretation

The main Day 19 finding is that feature-based affine registration needs more than a successful OpenCV return value. Correspondence geometry, RANSAC consensus, transform plausibility, and ground-truth accuracy must be checked separately.

The model comparison also shows why the transform family matters. Similarity is sufficient when isotropic scale and rotation describe the geometry. The controlled affine cases require additional freedom for anisotropic scale and shear, and the affine model recovered those cases much more accurately when usable correspondences were available.

## Failure cases

`low_texture_affine` failed because too few RANSAC inliers remained. `repeated_pattern_affine` failed earlier because descriptor filtering produced no accepted matches at the default threshold.

Both failures remain in the result tables and summaries.

## Limitations

- The current thresholds are development settings.
- The texture classification is specific to the configured gradient-energy thresholds.
- ORB keypoint counts are capped by the configured feature limit.
- The repeated checkerboard is a controlled ambiguity probe, not a representative sample of all repeated real-world structure.
- The model comparison is limited to the current controlled cases.
- Runtime values are machine-dependent and should be interpreted with the target environment recorded.

## Decision and next experiment

Day 20 should integrate the validated feature-based similarity and affine methods into one benchmark and compare them fairly with Phase Correlation and ECC only on compatible cases and motion models.
