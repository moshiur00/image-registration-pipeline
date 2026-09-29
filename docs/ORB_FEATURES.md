# ORB Feature Detection and Descriptor Extraction

## Purpose

Day 16 introduces the feature-detection layer for the feature-based registration stage. The goal is to detect local image structures and compute binary descriptors before descriptor matching or RANSAC is introduced.

The implementation deliberately keeps detection separate from matching. This makes it possible to measure whether the images contain enough useful local structure before later stages try to establish correspondences or estimate a transform.

## ORB output

For each detected feature, the project stores:

- geometric point `(x, y)`;
- keypoint size;
- orientation in degrees;
- response value;
- pyramid octave;
- class identifier;
- one 32-byte binary ORB descriptor.

The detector also records runtime, image shape, success status, and a specific failure reason when no descriptors can be produced.

## Configuration

The current experiment exposes the main OpenCV ORB settings:

- `n_features`;
- `scale_factor`;
- `n_levels`;
- `edge_threshold`;
- `first_level`;
- `wta_k`;
- `score_type`;
- `patch_size`;
- `fast_threshold`.

The default Day 16 experiment uses a maximum of 800 features with the Harris score, eight pyramid levels, scale factor 1.2, patch size 31, and FAST threshold 20.

## Input handling

ORB is applied to 2D grayscale images. Non-uint8 intensity images are converted deterministically to the uint8 range required by OpenCV. Constant images are accepted as valid input but normally return a safe `no_keypoints_detected` result rather than raising an exception.

Optional masks are supported. Mask values are converted to a binary OpenCV mask, and detected keypoints are restricted to the valid region.

## Spatial coverage

A large feature count is not enough to show that the features are geometrically useful. The current implementation therefore records a simple grid-coverage measure.

The image is divided into a 4 x 4 grid. Spatial coverage is the fraction of grid cells that contain at least one detected keypoint.

This is only a descriptive diagnostic. It does not prove that the features are repeatable or correctly matched. Those questions belong to Day 17.

## Day 16 controlled cases

The configured development experiment uses tracked `camera`, `coins`, and `moon` source images and evaluates detection after:

- identity;
- translation;
- rotation;
- isotropic scale change;
- illumination gradient;
- Gaussian blur.

Geometric cases are generated from exact Moving -> Fixed transforms already supported by the benchmark infrastructure.

## Validated Day 16 observation

The target Windows run produced descriptors in both fixed and moving images for all eight configured cases.

Several camera cases reached the configured `n_features = 800` limit. Those counts are capped values, so they should not be interpreted as the total number of detectable camera features.

Blur reduced the available feature count substantially. In the configured camera blur case, the moving image produced 394 keypoints compared with the 800-feature cap in the fixed image. In the configured moon blur case, the moving image produced 36 keypoints compared with 585 in the fixed image. The moon blur case also had the lowest measured 4 x 4 spatial coverage, 0.375.

These are detection observations only. They do not yet establish whether the surviving keypoints form correct or stable correspondences.

The validated target-machine aggregate values were 652.0 mean moving-image keypoints, 0.695 mean moving-image spatial coverage, and 4.489 ms mean moving-image detection runtime. Runtime is machine-specific.

## Interpretation boundary

Day 16 does not report registration accuracy, TRE, matching precision, or RANSAC inlier quality. No geometric method comparison should be made from these results.

Day 17 added Hamming-distance descriptor matching and correspondence filtering. Those results measure correspondence availability and spatial support, while geometric consistency is evaluated separately by the Day 18 RANSAC stage.

## Files

- implementation: `src/image_registration/orb.py`
- configuration: `configs/week04_day01_orb_features.yaml`
- experiment script: `scripts/week04_day01_orb_features.py`
- tests: `tests/test_orb.py`
- compact report: `reports/week04_day01_orb_features.json`
- daily summary: `docs/daily/day_16_summary.md`
