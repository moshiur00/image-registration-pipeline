# Integrated Feature-Based Baseline Comparison

## Purpose

Day 20 integrates the validated Week 4 feature-based methods with the existing Phase Correlation and ECC baselines on explicitly shared monomodal cases. The goal is not to create one overall method ranking. The goal is to compare methods only where the underlying geometric task is sufficiently compatible.

## Comparison policy

Three shared comparison groups are used.

### Translation

The same four translation cases are evaluated with:

- Phase Correlation;
- ECC Translation;
- ORB + RANSAC Similarity.

ORB Similarity has more model freedom than a pure translation model, but all three methods receive the same translation-only ground truth. Results are reported case by case and as group summaries.

### Rigid

The same three rigid cases are evaluated with:

- ECC Rigid;
- ORB + RANSAC Similarity.

ORB Similarity includes isotropic scale while ECC Rigid does not. This is therefore a shared-case behavior comparison, not an equal-complexity model comparison.

### Affine

The same four affine cases are evaluated with:

- ECC Affine Single Resolution;
- ECC Affine Multiresolution;
- ORB + RANSAC Affine.

This is the closest direct model-family comparison because all three methods estimate affine geometry.

## Separate feature diagnostics

Two cases are intentionally kept outside the shared method comparisons:

- low-texture affine;
- repeated-pattern affine.

These cases are used to preserve feature-specific failure evidence. They should not be mixed into the cross-family comparison because their purpose is diagnostic rather than ranking.

## Target Windows observations

The validated target Windows run contains 13 cases and 32 registrations. It produced 30 method-level successes and 26 results inside the configured Day 20 development tolerances. The full repository test suite also completed with 314 passed in 4.36s.

### Translation shared cases

- Phase Correlation: 4 / 4 within tolerance, median TRE 0.043 px.
- ECC Translation: 4 / 4 within tolerance, median TRE 0.485 px.
- ORB + RANSAC Similarity: 3 / 4 within tolerance, median TRE 0.177 px.

The ORB similarity failure occurred on the blurred translation case, where the recovered TRE was 1.783 px. This is useful because the method still returned a geometric estimate, but that estimate did not satisfy the translation development threshold.

### Rigid shared cases

- ECC Rigid: 2 / 3 within tolerance, median TRE 0.262 px.
- ORB + RANSAC Similarity: 3 / 3 within tolerance, median TRE 0.369 px.

The ECC rigid failure occurred on the occluded coins case with a large geometric error. The ORB feature path remained within tolerance on that controlled case. This is a case-specific result and should not be generalized to all occlusion conditions.

### Affine shared cases

- ECC Affine Single Resolution: 3 / 4 within tolerance, median TRE 0.952 px.
- ECC Affine Multiresolution: 3 / 4 within tolerance, median TRE 0.977 px.
- ORB + RANSAC Affine: 4 / 4 within tolerance, median TRE 0.327 px.

Both ECC affine variants failed geometrically on the moon affine case in the target Windows run, while ORB + RANSAC Affine remained within tolerance. The multiresolution strategy therefore did not rescue every affine case, even though it improved capture range in earlier controlled experiments.

## Feature diagnostic cases

The low-texture case failed before geometric estimation because too few fixed-image descriptors were available for KNN matching.

The repeated-pattern case produced filtered matches and an affine estimate, but only 7 RANSAC inliers remained. The estimate was rejected for insufficient RANSAC inliers and the transform violated several plausibility checks. The resulting TRE was 107.429 px. This is an important example of why feature count and match count are not enough to establish geometric correctness.

## Reporting interpretation

The integrated benchmark supports several reporting rules:

1. Keep translation, rigid, and affine comparisons separate.
2. Keep optimizer or estimator success separate from ground-truth geometric success.
3. Treat feature-specific failure probes separately from shared cross-family comparisons.
4. Do not infer universal method superiority from this compact controlled subset.
5. Preserve per-case failures because they explain where each registration family loses reliability.

## Current limitation

These are validated development-stage monomodal results. The thresholds are not final benchmark thresholds, the case count is intentionally compact, and multimodal registration has not yet been integrated. Runtime values remain machine-dependent.
