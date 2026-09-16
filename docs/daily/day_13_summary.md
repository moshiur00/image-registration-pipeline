# Day 13 Summary

## Week 3 Day 3: ECC Translation and Rigid Registration

**Status:** Implementation complete, local validation pending on the target Windows environment.

## Objective

Implement the first iterative intensity-based registration baseline using ECC, support translation and rigid motion, compare identity and phase-correlation initialization, and evaluate every estimate against exact Week 2 ground truth.

## Implemented

- Added `ECCRegistration` using OpenCV `findTransformECC`.
- Added translation and rigid motion models.
- Preserved the project-wide Moving -> Fixed transform convention by explicitly converting OpenCV's returned warp direction.
- Added identity initialization.
- Added phase-correlation coarse initialization.
- Added configurable maximum iterations, epsilon, Gaussian filter size, interpolation, and optional minimum ECC threshold.
- Added final ECC objective recording.
- Added estimation, warping, and total runtime diagnostics.
- Added safe optimizer failure records instead of uncaught ECC errors.
- Added mean TRE from known control points.
- Added centered translation-parameter error.
- Added rigid rotation error in degrees.
- Added NCC before and after registration.
- Added CSV and JSON result tables, summary JSON, plots, and representative figures.
- Added a tracked compact report snapshot for later technical-report generation.
- Added automated ECC, ground-truth metric, and report-snapshot tests.

## Controlled validation design

The source image is resized to 256 x 256 for the Day 3 iterative experiment.

The configuration defines 12 base cases:

- six translation cases;
- six rigid cases;
- clean geometry;
- selected contrast changes;
- selected illumination gradients;
- one deliberately challenging rigid case for initialization sensitivity.

Every case is run with:

```text
identity initialization
phase-correlation initialization
```

This produces 24 registrations.

## Selected development tolerances

```text
Mean TRE <= 1.0 pixel
Translation parameter error <= 1.5 pixels
Rigid rotation error <= 1.0 degree
```

These are Week 3 development criteria and are not yet the final Week 6 benchmark success policy.

## Reference development run

```text
Optimizer successes: 23/24
Within tolerance:    23/24

translation + identity:          6/6
translation + phase correlation: 6/6
rigid + identity:                5/6
rigid + phase correlation:       6/6
```

Median mean TRE in the reference run was approximately:

```text
translation + identity:          0.267 px
translation + phase correlation: 0.274 px
rigid + identity:                0.255 px
rigid + phase correlation:       0.255 px
```

The deliberately challenging rigid case used +20 degrees rotation and (+50, -35) pixel translation. Identity initialization failed to converge, while phase-correlation initialization converged with approximately 0.339 pixel mean TRE.

This controlled case demonstrates initialization sensitivity without claiming that phase initialization is always better.

## Report preservation

Complete run artifacts remain under `outputs/` and are excluded from Git because they contain generated figures and potentially large data.

A compact machine-readable result snapshot is written to:

```text
reports/week03_day03_ecc_translation_rigid.json
```

The project now also contains `reports/progress_registry.json`, Week 1 and Week 2 summary snapshots, and compact Week 3 Day 1 and Day 2 result snapshots. This provides a tracked quantitative layer for future report generation in addition to daily and weekly narrative documentation.

## Next step

Run the complete automated test suite and Day 3 ECC experiment on the target Windows environment. After local validation, Week 3 Day 4 will extend ECC to affine motion and add coarse-to-fine multiresolution pyramids.
