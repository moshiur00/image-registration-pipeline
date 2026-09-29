# Day 20 Summary: Integrated Feature-Based Benchmark

## Status

Complete and validated on the target Windows environment.

## Purpose

Day 20 integrates the frequency-based, intensity-based, and feature-based registration paths into one controlled monomodal comparison while preserving fair comparison boundaries.

## Implemented

- integrated case runner for Phase Correlation, ECC, ORB matching, similarity RANSAC, and affine RANSAC;
- shared translation, rigid, and affine comparison groups;
- separate low-texture and repeated-pattern feature diagnostics;
- model-aware TRE and parameter-error checks;
- common result records containing success, failure reason, geometric error, runtime, overlap, image similarity, and feature diagnostics;
- representative registration and feature-match figures;
- shared-case TRE plots;
- compact tracked report snapshot and full local JSON/CSV outputs;
- explicit fair-comparison policy to prevent unrelated motion models from being combined into one ranking.

## Target Windows validation

- full repository test suite: 314 passed in 4.36s;
- integrated benchmark: 13 cases and 32 method executions;
- method-level successes: 30 / 32;
- inside the configured Day 20 development tolerances: 26 / 32.

### Translation shared cases

- Phase Correlation: 4 / 4 within tolerance, median TRE 0.043 px.
- ECC Translation: 4 / 4 within tolerance, median TRE 0.485 px.
- ORB + RANSAC Similarity: 3 / 4 within tolerance, median TRE 0.177 px.

The ORB similarity estimate on the blurred translation case returned 1.783 px TRE and did not meet the translation tolerance.

### Rigid shared cases

- ECC Rigid: 2 / 3 within tolerance, median TRE 0.262 px.
- ORB + RANSAC Similarity: 3 / 3 within tolerance, median TRE 0.369 px.

On the occluded coins case, ECC Rigid returned 119.557 px TRE while the feature-based similarity path returned 0.388 px TRE. This is a case-specific observation from the current controlled subset.

### Affine shared cases

- ECC Affine Single Resolution: 3 / 4 within tolerance, median TRE 0.952 px.
- ECC Affine Multiresolution: 3 / 4 within tolerance, median TRE 0.977 px.
- ORB + RANSAC Affine: 4 / 4 within tolerance, median TRE 0.327 px.

On the moon affine case, ECC Affine Single returned 39.139 px TRE, ECC Affine Multiresolution returned 109.342 px TRE, and ORB + RANSAC Affine returned 0.315 px TRE. Multiresolution ECC improved capture range in earlier controlled experiments but did not guarantee recovery on this integrated case.

## Feature diagnostic failures

### Low texture

The low-texture case produced only one fixed-image ORB keypoint and failed before KNN matching with `insufficient_fixed_descriptors_for_knn`.

### Repeated pattern

The repeated-pattern case produced 62 filtered matches but only 7 RANSAC inliers. The affine estimate was rejected for `insufficient_ransac_inliers` and the returned TRE was 107.429 px.

## Findings

- Shared-case grouping keeps the comparison interpretable and avoids mixing unrelated motion models into one ranking.
- A returned transform is not enough to establish registration quality. Ground-truth TRE remains the decisive geometric check on controlled cases.
- Feature-based registration remained effective on some occlusion and affine cases where the current ECC configuration failed, but this observation is limited to the current controlled subset.
- Low texture and repetitive structure produced different feature failure mechanisms. One failed because descriptors were unavailable, while the other produced ambiguous correspondences that did not support a reliable transform.
- Multiresolution ECC improved capture range in earlier experiments but did not guarantee recovery on every affine case in the integrated subset.

## Limitations

- Day 20 thresholds are development thresholds, not final benchmark thresholds.
- The rigid comparison is not an equal-complexity comparison because ORB Similarity includes isotropic scale.
- The compact monomodal subset supports controlled observations, not universal method rankings.
- Multimodal comparison remains outside the current stage and is reserved for mutual-information registration.
- Runtime values are specific to the target machine and current implementation settings.

## Decision

Week 4 is complete. The shared-case comparison policy, explicit failure records, and common result schema will carry forward into the multimodal mutual-information stage.
