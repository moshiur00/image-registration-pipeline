# ORB Descriptor Matching and Correspondence Filtering

## Purpose

Day 17 adds descriptor matching after the ORB detection stage. The goal is to establish candidate correspondences between moving-image and fixed-image keypoints without fitting a geometric transform yet.

The project keeps this stage separate from RANSAC so descriptor quality can be studied independently from geometric model estimation.

## Matching direction

The stored registration convention remains Moving -> Fixed.

For descriptor matching:

- moving descriptors are used as query descriptors;
- fixed descriptors are used as the reference descriptors;
- each accepted match therefore maps one moving keypoint to one fixed keypoint.

## Hamming distance

ORB produces binary descriptors. Descriptor similarity is therefore measured with Hamming distance.

A lower Hamming distance means fewer differing descriptor bits. This can indicate stronger local appearance similarity, but it is not a geometric correctness measure.

## KNN ratio filtering

For each moving descriptor, the two nearest fixed descriptors are found.

If their distances are `d1` and `d2`, the match is accepted when:

```text
d1 / d2 < ratio_threshold
```

A smaller ratio threshold is stricter. A larger threshold retains more candidate correspondences but can also keep more ambiguous matches.

The configured Day 17 development sweep uses:

```text
0.60, 0.70, 0.75, 0.80, 0.90
```

The default reporting threshold is `0.75`.

## Cross-check matching

Cross-check matching accepts a correspondence only when the moving descriptor selects the fixed descriptor as its nearest neighbor and the fixed descriptor also selects the moving descriptor as its nearest neighbor.

This is a different filtering rule from the KNN ratio test. Match counts from the two approaches should not be interpreted as direct quality rankings before geometric validation.

## Correspondence spatial coverage

Accepted matches are also evaluated using a 4 x 4 grid in each image.

The project records:

- fixed-image endpoint coverage;
- moving-image endpoint coverage;
- minimum of the two coverages.

This matters because a large number of matches concentrated in one local region may still provide weak support for estimating a global similarity or affine transform.

## Safe failures

The matching layer records explicit failure reasons instead of raising an expected-content error when:

- fixed descriptors are unavailable;
- moving descriptors are unavailable;
- too few filtered matches remain;
- too few fixed descriptors are available for a 2-nearest-neighbor query;
- OpenCV matching returns an error.

Invalid configuration values still raise `ValueError` because they indicate a caller or configuration problem.

## Day 17 scope boundary

Day 17 does not estimate a registration transform and does not calculate TRE from the matches.

A match can pass descriptor filtering and still be geometrically wrong. Day 18 will add RANSAC similarity estimation so accepted correspondences can be separated into geometric inliers and outliers.
