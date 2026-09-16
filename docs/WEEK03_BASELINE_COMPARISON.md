# Week 3 Integrated Baseline Comparison

## Purpose

Week 3 Day 5 consolidates the monomodal registration methods developed during Days 11 to 14 into one standardized benchmark. The goal is to preserve comparable output fields, reuse known synthetic ground truth, and produce a compact baseline table for later report generation.

The benchmark does not force every method onto every transformation family. Each method is evaluated only on a supported motion model:

- phase correlation: translation;
- ECC translation: translation;
- ECC rigid: rigid;
- ECC affine single resolution: affine;
- ECC affine multiresolution: affine.

The only direct cross-method accuracy comparison is phase correlation versus ECC translation on the same translation cases. The rigid and affine results are reported as supported baselines rather than as a universal ranking.

## Benchmark composition

The Day 5 configuration uses three tracked real grayscale source images: `camera`, `coins`, and `moon`. Each source is resized to 256 x 256 before deterministic synthetic geometry is applied.

The benchmark contains 14 base cases and 24 registration runs:

- six translation cases, each evaluated by phase correlation and ECC translation;
- four rigid cases, evaluated by ECC rigid;
- four affine cases, each evaluated by single-resolution and multiresolution ECC.

Conditions include clean data, Gaussian noise, Gaussian blur, contrast change, illumination gradient, restricted field of view, and a difficult affine capture-range case.

## Standard result schema

Every registration record contains:

- case ID and source ID;
- condition and motion model;
- method ID and initialization;
- optimizer success and geometric pass/fail status;
- failure reason;
- mean TRE;
- centered translation parameter error;
- rigid rotation error where applicable;
- affine linear-component error where applicable;
- overlap fraction;
- NCC and SSIM before and after registration;
- phase-correlation response or final ECC value;
- pyramid levels completed where applicable;
- runtime;
- exact ground-truth and estimated Moving -> Fixed transforms;
- condition metadata.

The development pass/fail rule uses the Week 3 geometric tolerances in the configuration. These are development checks, not the final cross-dataset success policy. The unified success/failure policy is scheduled for Week 6.

## Visual outputs

Representative runs store:

- fixed image;
- moving image;
- registered image;
- valid-overlap mask;
- alpha overlays before and after registration;
- checkerboards before and after registration;
- absolute-difference images before and after registration;
- edge overlays before and after registration;
- fixed/moving/registered comparison figure.

## Reference development run

The development run completed 24 registrations. Twenty-three returned optimizer success and 21 satisfied the selected geometric tolerances.

Reference method summaries:

```text
Phase correlation
6/6 within tolerance
median TRE: 0.034 px

ECC translation
4/6 within tolerance
median TRE: 0.290 px

ECC rigid
4/4 within tolerance
median TRE: 0.295 px

ECC affine single resolution
3/4 within tolerance
median TRE: 0.733 px

ECC affine multiresolution
4/4 within tolerance
median TRE: 0.661 px
```

The reference run preserved two useful failure cases. ECC translation did not satisfy the geometric criterion for the blurred Moon translation case and failed on the restricted-field-of-view translation case. Phase correlation remained within tolerance on all six translation cases in this small controlled subset.

The affine capture-range case again separated single-resolution from multiresolution ECC. Single-resolution ECC returned an optimizer result but produced a large geometric error, while the multiresolution configuration recovered a transform within the selected tolerance.

These observations are specific to the current controlled benchmark. They should not be interpreted as a general ranking across registration methods or datasets.

## Stored outputs

Full run artifacts are written to:

```text
outputs/week03_day05_integrated_baselines/
```

The tracked compact snapshot is written to:

```text
reports/week03_day05_integrated_baselines.json
```

This snapshot, together with the daily and weekly summaries, is intended to support final report generation without requiring the local `outputs/` directory.
