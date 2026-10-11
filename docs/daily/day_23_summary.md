# Day 23 Summary: Affine Mutual Information and Multiresolution Capture Range

## Status

Day 23 is complete on the target Windows environment. The full suite passed with `352 passed in 8.68s`, and the 17-registration controlled experiment completed without method-execution failures.

Latest validated project state before Day 23:

- Day 22 target Windows suite: `347 passed in 8.65s`;
- Day 22 frozen rigid MI confirmation: 5 / 5 within tolerance;
- Day 22 frozen median TRE: 0.0173 px;
- Day 22 frozen maximum TRE: 0.0950 px.

## Objective

Extend the validated 2D Mattes Mutual Information path from rigid to affine registration while keeping the Day 22 metric, optimizer, initialization, sampling, and preprocessing choices frozen.

Day 23 focuses on two questions:

1. Can affine MI recover known affine geometry under monomodal and simulated multimodal appearance changes?
2. Does the existing coarse-to-fine pyramid improve capture range relative to single-resolution affine MI on the same controlled cases?

A small rigid comparator is retained only on selected true-affine cases to demonstrate transform-model mismatch where meaningful. It is not a universal ranking against affine MI.

## Implementation

`src/image_registration/mutual_information.py` now provides `MutualInformationAffineRegistration` using SimpleITK `AffineTransform(2)` with the same Mattes MI and optimizer configuration interface as the validated rigid path.

The affine path preserves:

- SimpleITK physical coordinates;
- project transform direction `Moving -> Fixed`;
- full, regular, or random MI sampling support through the shared configuration;
- identity, geometry, and moments initialization support;
- Regular Step Gradient Descent;
- optimizer scaling from physical shift;
- multiresolution shrink factors and smoothing sigmas;
- iteration-level metric traces;
- optimizer stop condition and valid metric-point counts;
- explicit method failure records.

Day 23 additionally records affine transform plausibility diagnostics using determinant, principal scales, condition number, shear, reflection, and a broad translation guardrail. Plausibility is reported separately from optimizer execution and geometric tolerance status.

## Frozen Day 22 choices

Day 23 reuses:

- initialization: identity;
- histogram bins: 32;
- metric sampling: full;
- preprocessing: Gaussian smoothing with sigma 1.0;
- learning rate: 2.0;
- minimum step: 0.001;
- iterations: 200;
- relaxation factor: 0.5;
- gradient magnitude tolerance: 0.0001.

The multiresolution variant uses shrink factors `[4, 2, 1]` and smoothing sigmas `[2.0, 1.0, 0.0]`. The single-resolution control changes only the pyramid to `[1]` and `[0.0]`.

## Controlled cases

Seven known-ground-truth affine cases are configured:

- mild monomodal camera affine;
- medium affine with intensity inversion;
- affine with nonlinear gamma mapping;
- coins affine with multiplicative bias field;
- affine with histogram remapping;
- affine with restricted field of view and intensity inversion;
- moon affine with edge-emphasized appearance.

Each case is run with affine single-resolution and affine multiresolution MI. Three selected true-affine cases are also run with rigid multiresolution MI as model-mismatch diagnostics.

## Evaluation

Each successful method execution records:

- TRE in pixels;
- affine linear-component Frobenius error;
- centered translation error in pixels;
- affine plausibility diagnostics;
- final Mattes MI value;
- optimizer iteration and stop condition;
- valid metric points;
- runtime;
- method success;
- transform plausibility;
- geometric within-tolerance status;
- failure reason when applicable.

Local detailed evidence under `outputs/week05_day03_mi_affine_multiresolution/` includes per-case JSON, comparison images, joint histograms before and after registration, metric traces, aggregate CSV, and full results JSON. `outputs/` remains local and is not included in the normal shared project ZIP.

Tracked compact evidence is written to:

- `reports/week05_day03_mi_affine_multiresolution.json`.

## Validation rule

Failures must remain in the evidence. The Day 22 MI settings must not be retuned using Day 23 cases. Optimizer execution, transform plausibility, and geometric correctness are separate outcomes.

The affine transform-direction unit test verifies that the returned project transform is the exact inverse of the SimpleITK Fixed -> Moving transform. It intentionally does not require an affine MI optimizer to return an exact identity matrix for an identical smooth image, because that would mix transform-convention validation with optimizer/geometric-accuracy validation.

## Target Windows results

Target Windows validation:

- full suite: `352 passed in 8.68s`;
- affine single-resolution: 7 / 7 method successes, 7 / 7 plausible transforms, 5 / 7 within tolerance, median TRE 0.1681 px;
- affine multiresolution: 7 / 7 method successes, 7 / 7 plausible transforms, 5 / 7 within tolerance, median TRE 0.0887 px;
- paired outcome: 5 both-pass, 0 multiresolution-only pass, 0 single-resolution-only pass, 2 both-CHECK;
- rigid model-mismatch comparator: 0 / 3 within tolerance, median TRE 13.986 px.

The multiresolution variant improved median geometric accuracy on this controlled set but did not increase the number of cases inside tolerance. Therefore, Day 23 does not demonstrate a capture-range expansion from the pyramid on these seven cases.

The two preserved affine failures are `camera_affine_partial_overlap` and `moon_affine_edge`. Both optimizers executed and returned plausible transforms, but the estimates remained geometrically incorrect. This again shows that optimizer completion and plausibility do not imply correct registration.

The restricted rigid comparator failed all three selected true-affine cases, supporting transform-model mismatch as a distinct failure mechanism for these examples.

## Decision and next step

Day 23 is frozen and complete. Do not retune the Day 22 MI configuration using these Day 23 cases. Day 24 may now begin with real RIRE CT/MR-T1 physical-space registration, strict metadata preservation, and evidence limits based on the ground truth actually available.
