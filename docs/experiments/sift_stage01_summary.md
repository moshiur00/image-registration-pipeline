# SIFT Extension Stage 1: Detection and L2 Matching

## Status

Complete. Target Windows validation passed.

## Purpose

Establish SIFT detection, 128-dimensional floating-point descriptors, and L2 ratio-filtered matching before introducing geometric model estimation.

## Experimental setup

The development subset uses seven tracked monomodal cases:

- camera identity;
- camera rotation;
- camera scale;
- camera blur;
- camera partial overlap;
- coins rotation;
- moon blur.

The default SIFT feature limit is 800. The provisional KNN ratio threshold is 0.75. A ratio sweep covers 0.60, 0.70, 0.75, 0.80, and 0.85.

## Validated target Windows results

All seven cases retained at least eight accepted SIFT matches at the provisional threshold.

- mean accepted matches: 359.0;
- median accepted matches: 393.0;
- mean minimum correspondence coverage: 0.759;
- mean total fixed plus moving SIFT detection runtime: 79.382 ms on the target Windows environment;
- mean L2 matching runtime: 3.425 ms on the target Windows environment.

Full repository validation: 327 passed in 9.44s.

Case-level observations at ratio threshold 0.75:

- camera identity: 791 accepted matches, coverage 0.938;
- camera rotation: 437 accepted matches, coverage 0.750;
- camera scale: 393 accepted matches, coverage 0.812;
- camera blur: 57 accepted matches, coverage 0.688;
- camera partial overlap: 434 accepted matches, coverage 0.750;
- coins rotation: 390 accepted matches, coverage 1.000;
- moon blur: 11 accepted matches, coverage 0.375.

The ratio sweep increased mean accepted matches from 341.4 at 0.60 to 380.7 at 0.85. This does not establish that the looser threshold is better because Stage 1 does not measure geometric inliers or TRE.

## Observations

Blur reduced the number of usable SIFT correspondences substantially on both the camera and moon cases. The moon blur case was the weakest case, with 11 accepted matches and 0.375 spatial coverage.

The rotated coins case retained broad spatial support with full 4 x 4 grid coverage in the validated target run.

## Interpretation

SIFT can provide enough candidate correspondences across the selected controlled cases, including rotation and moderate scale change. Match count alone is not evidence of correct registration. Stage 2 must apply RANSAC and compare estimated geometry against known ground truth.

## Limitations

- no RANSAC transform is estimated yet;
- no TRE or parameter error is reported in Stage 1;
- the subset is intentionally small;
- runtime values are machine-dependent;
- runtime values are machine-dependent, so the target Windows runtimes should be treated as environment-specific measurements.

## Decision

Stage 1 is complete. Carry ratio threshold 0.75 provisionally into Stage 2. Keep the threshold configurable and use geometric consistency, TRE, failure rate, and runtime to decide whether another value is justified.
