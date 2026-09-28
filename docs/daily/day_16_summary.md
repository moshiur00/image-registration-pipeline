# Day 16 Summary: ORB Keypoint Detection and Descriptor Extraction

## Status

Complete and validated on the target Windows environment.

The full pytest suite reached 100% and returned exit code 0 on the target Windows project environment. The console capture did not include the final numeric pytest summary, so this record does not infer a target-machine pass count. The Day 16 ORB experiment also completed successfully for all 8 configured cases.

## 1. Purpose

The purpose of Day 16 was to introduce the first feature-based component without adding descriptor matching or RANSAC yet. The experiment asks whether ORB can detect and describe useful local structures across the tracked images and selected controlled changes.

## 2. Setup

Tracked source images:

- `camera`
- `coins`
- `moon`

Configured ORB settings:

- maximum features: 800
- scale factor: 1.2
- pyramid levels: 8
- Harris score
- patch size: 31
- FAST threshold: 20
- spatial-coverage grid: 4 x 4

Eight controlled cases were used:

1. camera identity
2. camera translation `(tx = 24, ty = -18)`
3. camera rotation `20 degrees`
4. camera isotropic scale `1.15`
5. camera diagonal illumination gradient
6. camera Gaussian blur `sigma = 3`
7. coins rotation `-15 degrees`
8. moon Gaussian blur `sigma = 3`

## 3. Variables changed

The source image and controlled image condition were changed across cases. ORB configuration remained fixed so changes in feature availability could be observed without mixing detector-parameter changes into the experiment.

## 4. Factors kept fixed

- ORB configuration
- grayscale input handling
- 4 x 4 spatial-coverage definition
- deterministic geometric generation
- project Moving -> Fixed transform convention
- tracked source images

## 5. Metrics and diagnostics

For fixed and moving images the script records:

- keypoint count
- descriptor count
- descriptor length
- mean, median, minimum, and maximum keypoint response
- 4 x 4 spatial coverage
- detection runtime
- safe failure reason

The experiment also records the moving-to-fixed keypoint-count ratio and the change in spatial coverage.

## 6. Target Windows results

All eight configured cases produced descriptors in both fixed and moving images.

| Case | Fixed keypoints | Moving keypoints | Moving coverage |
|---|---:|---:|---:|
| camera_identity | 800 | 800 | 0.750 |
| camera_translation | 800 | 800 | 0.625 |
| camera_rotation | 800 | 800 | 0.688 |
| camera_scale | 800 | 800 | 0.875 |
| camera_illumination | 800 | 800 | 0.750 |
| camera_blur | 800 | 394 | 0.562 |
| coins_rotation | 794 | 786 | 0.938 |
| moon_blur | 585 | 36 | 0.375 |

Validated aggregate values:

- configured cases: 8
- cases producing descriptors in both images: 8 / 8
- mean moving-image keypoint count: 652.0
- median moving-image keypoint count: 800.0
- mean moving-image 4 x 4 spatial coverage: 0.695
- mean moving-image detection runtime: 4.489 ms

Runtime is machine-specific and should be interpreted as the target Windows measurement for this configuration, not as a universal ORB runtime.

## 7. Observations

The camera identity, translation, rotation, scale, and illumination cases all reached the configured 800-feature cap in the moving image. Their counts are therefore censored by configuration and do not represent the total number of potentially detectable features.

Gaussian blur reduced feature availability. The camera blur case dropped from the 800-feature cap in the fixed image to 394 moving-image keypoints. The moon blur case dropped from 585 fixed-image keypoints to 36 moving-image keypoints, a moving-to-fixed count ratio of about 0.062. It also had the lowest measured spatial coverage at 0.375.

The rotated coins image retained 786 moving-image keypoints and had the highest measured moving-image spatial coverage in this experiment at 0.938.

The geometric camera cases retained the configured maximum number of features, but their spatial coverage changed. For example, translation reduced moving-image coverage from 0.750 to 0.625, while the scale case produced 0.875 coverage. This shows why feature count and feature distribution should be recorded separately.

## 8. Interpretation

The main Day 16 finding is that feature availability depends on both image content and image condition. Moderate geometric changes did not reduce the capped camera feature count in these cases, while blur substantially reduced the number and spatial support of detected features, especially for the moon image.

A large feature count does not prove that a transform can be estimated correctly. Features can fail to repeat at corresponding locations, produce ambiguous descriptors, or be distributed in a geometrically weak pattern. Descriptor matching is required before correspondence quality can be evaluated.

The high coins coverage and the strong feature reduction in the blurred moon case provide useful contrasting cases for Day 17. They should help test whether descriptor filtering behaves differently when many well-distributed features are available versus when only a small number survive.

## 9. Failure cases

No configured Day 16 experiment failed to produce descriptors in both images.

The implementation still includes safe behavior for low-information input. A constant image returns `no_keypoints_detected` rather than producing an uncaught error.

## 10. Limitations

- Day 16 measures detection and descriptor extraction only.
- No feature correspondences are established yet.
- No registration transform is estimated.
- No TRE or parameter error is reported.
- Several camera cases hit the configured feature cap, so their counts cannot be compared as uncapped feature totals.
- Spatial coverage only measures occupied grid cells. It does not measure repeatability or geometric quality.
- The observations are specific to the tracked images, transformations, ORB settings, and target machine used for this experiment.

## 11. Decision and next experiment

Proceed to Day 17 with Hamming-distance descriptor matching, KNN matching, ratio filtering, cross-check comparison, match-distance diagnostics, and spatial distribution of accepted correspondences.

Day 17 should answer a different question from Day 16: not how many features are detected, but how many plausible correspondences survive filtering and how those correspondences are distributed across the image.
