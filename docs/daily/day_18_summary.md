# Day 18 Summary: ORB + RANSAC Similarity Estimation

## Objective

Add robust geometric model estimation after ORB descriptor matching. The goal is to determine which filtered correspondences agree with one similarity transform and to evaluate the estimated transform against known ground truth.

## Implementation

Day 18 adds:

- similarity estimation with OpenCV RANSAC;
- Moving -> Fixed transform conversion;
- configurable reprojection threshold, confidence, maximum trials, refinement iterations, minimum inliers, and minimum inlier ratio;
- inlier and outlier counts;
- reprojection residual statistics;
- TRE, rotation error, scale error, and centered translation error;
- registered-image and edge-overlay outputs;
- separate RANSAC inlier and outlier match visualizations;
- a controlled injected-outlier experiment;
- safe failure records for insufficient correspondences or failed estimation.

## Development experiment

The configured experiment uses camera and coins source images with controlled translation, rotation, isotropic scale, combined similarity transformations, blur, and illumination change.

The default descriptor stage uses ORB with KNN Hamming matching and a ratio threshold of 0.75. RANSAC then estimates the similarity transform from the accepted correspondences.

## Reporting rule

Three concepts remain separate:

1. Descriptor-filter success: enough matches survived the ratio filter.
2. RANSAC success: enough geometrically consistent inliers supported a model.
3. Geometric success: the estimated transform remained inside the configured ground-truth error thresholds.

A case is not reported as geometrically correct only because RANSAC returned a transform.

## Validation status

Day 18 is complete and validated on the target Windows environment. The full repository test suite passed with 283 tests and exit code 0. The tracked Day 18 report contains the refreshed target-machine experiment measurements.

## Next step

Day 19 will extend the feature-based model to general affine estimation and add degeneracy checks, texture-related diagnostics, and parameter sweeps.

## Target Windows evidence

The target Windows run completed all 8 configured cases:

```text
RANSAC success: 8 / 8
Within working tolerances: 8 / 8
Mean inlier ratio: 0.884
Median TRE: 0.277 px
Maximum TRE: 0.556 px
```

The smallest TRE occurred in `camera_similarity_illumination` at 0.110 px. The largest TRE occurred in `camera_similarity_large` at 0.556 px. The lowest inlier ratio occurred in `camera_similarity_blur` at 0.788.

The controlled outlier experiment used `camera_similarity_medium`. It injected 126 incorrect fixed-image endpoints into the accepted correspondence set. RANSAC rejected all 126 injected correspondences in the target Windows run, and the recovered transform produced 0.360 px TRE.

## Observation

The descriptor filter retained many correspondences, but RANSAC still classified a non-trivial subset as geometric outliers. This confirms why descriptor distance and geometric consistency should be treated as separate stages.

Blur reduced the inlier ratio more than the other configured Day 18 conditions, while the estimated transform still remained inside the current development thresholds. This is an observation for the current case set, not a general robustness claim.

## Interpretation

The current results show that RANSAC can recover the configured similarity transformations from the Day 17 ORB correspondences in these controlled cases. The injected-outlier experiment also provides direct evidence that the robust estimator can reject deliberately corrupted correspondences without losing the correct transform in that case.

## Limitations

- The Day 18 model is similarity only. General affine motion is not yet estimated by the feature-based method.
- The current thresholds are development thresholds and will be revisited during the unified evaluation stage.
- The recorded runtime values are target-machine measurements and remain machine-specific.
- The outlier-injection result is one controlled experiment and should not be generalized to arbitrary outlier structures.
