# Day 16 Summary: ORB Keypoint Detection and Descriptor Extraction

## Status

Implementation complete. Target Windows validation is pending.

The complete development-environment test suite currently contains 257 tests. In the available development environment, 253 passed and four SimpleITK-dependent tests were skipped because SimpleITK is not installed there. The last fully validated target Windows state before Day 16 remains 242 / 242 tests passed.

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

## 6. Development-run results

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

Development-run aggregate values:

- configured cases: 8
- cases producing descriptors in both images: 8 / 8
- mean moving-image keypoint count: 652.0
- mean moving-image 4 x 4 spatial coverage: 0.695

Runtime values are recorded in the compact report and full local output. They should be treated as machine-specific and should be replaced by the target Windows run before final reporting.

## 7. Observations

The camera identity, translation, rotation, scale, and illumination cases all reached the configured 800-feature cap in the moving image. This means their count is censored by configuration and does not show the total number of potentially detectable features.

Gaussian blur reduced the number of detected features. The camera blur case dropped to 394 moving-image keypoints. The moon blur case dropped from 585 fixed-image keypoints to 36 moving-image keypoints and had the lowest measured spatial coverage at 0.375.

The rotated coins image retained 786 moving-image keypoints and had high spatial coverage at 0.938 in this configured case.

## 8. Interpretation

The main Day 16 finding is that feature availability depends strongly on image content and condition. Blur can substantially reduce both keypoint count and spatial support, while textured content can retain many detected features under moderate geometric change.

A large number of detected keypoints does not prove that a transform can be estimated correctly. The features may not repeat at corresponding locations, may produce ambiguous descriptors, or may cluster in a geometrically weak region. These questions require descriptor matching and later RANSAC analysis.

## 9. Failure cases

No configured development case failed to produce descriptors in both images.

The implementation nevertheless includes safe behavior for low-information input. A constant image returns `no_keypoints_detected` instead of producing an uncaught error.

## 10. Limitations

- This stage measures detection and descriptor extraction only.
- No feature correspondences are established yet.
- No registration transform is estimated.
- No TRE or parameter error is reported.
- Several camera cases hit the configured feature cap, so their counts cannot be compared as uncapped feature totals.
- The current numerical observations are from the development environment and must be validated on the target Windows environment before Day 16 is marked complete.

## 11. Decision and next experiment

After target-machine validation, proceed to Day 17 with Hamming-distance descriptor matching, KNN matching, ratio filtering, cross-check comparison, match-distance diagnostics, and spatial distribution of accepted correspondences.

Day 17 should answer a different question from Day 16: not how many features are detected, but how many plausible correspondences survive filtering and how they are distributed across the image.
