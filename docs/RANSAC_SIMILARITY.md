# ORB + RANSAC Similarity Registration

Day 18 adds the first geometric model-estimation stage to the feature-based pipeline.

## Purpose

ORB detection and descriptor filtering produce candidate correspondences, but descriptor similarity alone does not prove that a correspondence is geometrically correct. RANSAC estimates a similarity transform while separating correspondences that agree with the model from those that do not.

The estimated transform follows the existing project convention:

```text
Moving -> Fixed
```

## Similarity model

The model contains four degrees of freedom:

```text
isotropic scale
rotation
translation x
translation y
```

OpenCV `estimateAffinePartial2D` is used with the RANSAC method. The returned 2 x 3 matrix is converted to the project's 3 x 3 homogeneous representation.

## RANSAC inputs and outputs

Input:

```text
accepted ORB correspondences
moving keypoint coordinates
fixed keypoint coordinates
```

Output diagnostics include:

```text
estimated Moving -> Fixed transform
input match count
inlier count
outlier count
inlier ratio
reprojection residuals
runtime
failure reason
```

The implementation fails safely when too few matches are available or OpenCV cannot estimate a valid model.

## Geometric evaluation

Known synthetic similarity transforms are used so the estimate can be evaluated independently of the RANSAC objective.

Day 18 records:

```text
TRE
rotation error
scale error
centered translation error
```

RANSAC success and geometric success are separate fields. A returned transform is not automatically considered correct.

## Development thresholds

The Day 18 configuration uses working thresholds for controlled development experiments:

```text
TRE <= 2.0 px
rotation error <= 1.0 degree
absolute scale error <= 0.03
centered translation error <= 3.0 px
```

These are development thresholds, not the final benchmark policy.

## Controlled outlier experiment

One configured similarity case deliberately corrupts 30 percent of the accepted descriptor correspondences by assigning incorrect fixed-image endpoints. The experiment records how many injected correspondences RANSAC rejects and whether the estimated transform remains geometrically accurate.

This directly tests the reason RANSAC is used after descriptor filtering.

## Current scope

Day 18 is limited to the similarity model. General affine RANSAC, transform plausibility checks, degeneracy detection, texture stratification, and threshold sweeps are planned for Day 19.
