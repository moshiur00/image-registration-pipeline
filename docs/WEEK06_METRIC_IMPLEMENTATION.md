# Week 6 Metric Implementation

## Purpose

Day 27 implements the metric semantics frozen by the Day 26 unified evaluation contract. The implementation is intentionally method-independent so Phase Correlation, ECC, feature-based registration, and Mutual Information can later write comparable result records without comparing their native optimizer objectives directly.

## Scientific separation

The project distinguishes three evidence levels:

1. **Ground-truth geometric evidence** such as transform-parameter error and TRE.
2. **Reference-mask evidence** such as Dice.
3. **Descriptive image evidence** such as MAE, MSE, NCC, SSIM, and evaluation Mutual Information.

Descriptive metrics can be calculated for unknown image pairs, but they do not independently establish geometric or anatomical correctness.

## Parameter error

`model_aware_parameter_errors()` compares exact reference and estimated homogeneous transforms.

- Translation error is the Euclidean difference between transform offset vectors.
- Pixel-space translation can also be converted to physical units using explicit spacing.
- Rigid and similarity models report the smallest absolute rotation difference.
- Similarity reports absolute isotropic scale error.
- Affine reports Frobenius error between linear components.
- 3D rigid rotation error is the angle of the relative rotation matrix.

The function does not force a rotation or scale interpretation onto a general affine matrix.

## TRE

TRE is implemented for both exact-transform and landmark-reference cases.

For exact transforms, the same source control points are mapped by the reference and estimated transforms. Euclidean distances between the resulting positions are summarized using:

- mean;
- median;
- population standard deviation;
- 95th percentile.

If spacing is supplied, the same coordinate differences are scaled axis by axis before physical distances are calculated.

## Dice

The Dice policy is explicit:

- identical non-empty masks: `1.0`;
- disjoint masks: `0.0`;
- both masks empty: `1.0` by project policy;
- exactly one mask empty: `0.0`.

Masks must be binary and have identical shape.

## Descriptive metrics and valid overlap

`overlap_aware_descriptive_metrics()` requires an explicit non-empty valid-overlap mask and calculates:

- MAE;
- MSE;
- NCC;
- SSIM;
- evaluation Mutual Information;
- valid-overlap fraction.

Warp borders and other invalid regions must be excluded from this mask. For masked SSIM, invalid pixels are neutralized for display-window computation so invalid borders do not leak into local SSIM neighborhoods.

## Evaluation Mutual Information

Evaluation MI uses a deterministic joint histogram and returns Mutual Information in natural-log units. It is a post-registration descriptive metric. It must not be directly compared with a Mattes MI optimizer objective, ECC objective, phase response, or RANSAC inlier ratio.

## Hand-constructed validation cases

Day 27 validates the implementation against independently known cases:

- a `(3, 4)` translation with exactly `5 px` Euclidean error;
- anisotropic spacing conversion;
- identity transform with zero TRE;
- rigid rotation wrap-around across 180 degrees;
- known similarity scale and rotation differences;
- known affine linear discrepancy;
- landmark TRE;
- perfect, disjoint, and empty-mask Dice cases;
- binary identical variables with MI equal to `ln(2)`;
- invalid border changes excluded by the overlap mask;
- explicit rejection of zero valid overlap.

## Multimodal caution

NCC and SSIM are useful for related intensity patterns, but modality changes can make them misleading. An aligned intensity-inverted pair can have a strongly negative NCC while Mutual Information still detects statistical dependence. This is why modality labels remain part of every future benchmark record.

## Scope boundary

Day 27 does not define success thresholds, rank methods, or select a recommended registration. Those tasks require the benchmark runner and robustness evidence from later Week 6 and Week 7 work.
