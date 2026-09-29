# Affine RANSAC, Degeneracy Checks, and Texture Diagnostics

Day 19 extends the feature-based registration path from similarity estimation to a general 2D affine model.

## Scope

The implementation estimates a Moving -> Fixed affine transform from ORB correspondences using OpenCV RANSAC. The affine model can represent translation, rotation, anisotropic scale, and shear.

The additional model freedom makes explicit failure checks important. Day 19 therefore evaluates four separate questions:

1. Are there enough filtered descriptor matches?
2. Are the correspondences spatially useful and non-collinear?
3. Does RANSAC find a consistent affine model?
4. Is the estimated transform geometrically plausible and close to known ground truth?

## Correspondence guardrails

Before model fitting, the estimator records:

- fixed-image grid coverage;
- moving-image grid coverage;
- minimum grid coverage;
- fixed-point linearity ratio;
- moving-point linearity ratio.

The linearity ratio is the minor-to-major covariance eigenvalue ratio of the 2D correspondence coordinates. Values near zero indicate that the points are close to one line, which is a degenerate configuration for stable affine estimation.

## Transform plausibility

After estimation, the affine linear block is checked using:

- determinant;
- minimum and maximum singular values;
- condition number;
- normalized column-angle cosine as a shear diagnostic;
- translation magnitude relative to the image diagonal;
- optional reflection rejection.

These checks do not prove that the transform is correct. They reject transformations that violate configured development bounds before a result is treated as a successful estimate.

## Texture diagnostics

The experiment stores two descriptive texture measurements:

- normalized Sobel gradient energy;
- ORB keypoint density per megapixel.

Configured gradient-energy thresholds divide cases into low, medium, and high texture groups. These labels are only experimental strata. They are not universal definitions of image texture.

## Model comparison

The same filtered ORB correspondences are passed to both similarity RANSAC and affine RANSAC. This creates a controlled comparison between a restricted model and a more flexible model.

For true similarity motion, the affine model should not be assumed better simply because it has more degrees of freedom. For true affine motion containing anisotropic scale or shear, the similarity model can underfit because it cannot represent the full transformation.

## Threshold sweep

The Day 19 sweep varies:

- ORB KNN ratio threshold: 0.60, 0.70, 0.75, 0.80, 0.90;
- RANSAC reprojection threshold: 1, 2, 3, 5 pixels.

The sweep includes textured, occluded, lower-texture, and repeated-pattern cases. TRE, success state, inlier ratio, accepted-match count, and failure reason are stored for every combination.

The purpose is to expose sensitivity, not to declare a globally optimal threshold.

## Failure labels

The affine estimator can report specific reasons including:

- `insufficient_matches`;
- `degenerate_correspondences_collinear`;
- `poor_spatial_coverage`;
- `ransac_estimation_failed`;
- `insufficient_ransac_inliers`;
- `low_inlier_ratio`;
- `near_singular_transform`;
- `reflection_not_allowed`;
- `implausible_principal_scale`;
- `implausible_condition_number`;
- `implausible_shear`;
- `implausible_translation`.

## Development-run observations

The initial development run used nine controlled cases.

- Seven of nine affine RANSAC cases succeeded and were inside the configured geometric tolerances.
- Median affine TRE was 0.555 px across cases with an estimated transform.
- The strongest successful result was `moon_affine` at 0.200 px TRE.
- `low_texture_affine` retained only eight descriptor matches, produced six RANSAC inliers, and was rejected for insufficient RANSAC inliers. Its returned transform had 15.599 px TRE, which shows why estimator success and geometric accuracy remain separate.
- `repeated_pattern_affine` produced no filtered matches at the default ratio threshold and failed before transform estimation.
- Affine RANSAC had lower TRE than similarity RANSAC on seven of the eight true-affine cases in this development run.
- The three explicit degeneracy and plausibility probes produced the intended failure labels for collinear correspondences, clustered correspondences, and implausible scale.
- The threshold sweep contained 120 combinations. The five textured and medium-texture cases were within tolerance across all tested combinations, while the low-texture and repeated-pattern cases remained failures across the sweep.

These values are development-environment observations. The target Windows run is required before Day 19 is marked complete.
