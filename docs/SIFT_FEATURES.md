# SIFT Feature Detection and Matching

## Purpose

SIFT is an optional feature front-end added after completion of the ORB + RANSAC baseline. The purpose is not to replace ORB automatically, but to test whether scale-space keypoints and floating-point descriptors provide a useful complementary capability on selected controlled cases.

## Descriptor representation

SIFT produces 128-dimensional floating-point descriptors. Matching therefore uses Euclidean L2 distance. This is intentionally different from the ORB path, where 32-byte binary descriptors use Hamming distance.

The two descriptor-distance values are not directly comparable across methods.

## Stage 1 scope

Stage 1 covers only:

- SIFT keypoint detection;
- 128-dimensional descriptor extraction;
- keypoint response and spatial-coverage diagnostics;
- L2 KNN descriptor matching;
- configurable ratio filtering;
- ratio-threshold sweep;
- match and correspondence-coverage visualizations;
- safe failure handling for images with insufficient features.

No RANSAC transform is estimated in Stage 1. Ground-truth registration error is therefore not used to choose a final SIFT threshold at this stage.

## Configuration

The Stage 1 configuration exposes:

- maximum feature count;
- octave-layer count;
- contrast threshold;
- edge threshold;
- base Gaussian sigma;
- spatial grid size;
- minimum accepted matches;
- ratio-test threshold;
- ratio-threshold sweep;
- optional maximum L2 distance.

## Matching convention

Moving-image descriptors are queries and fixed-image descriptors are the reference set. This preserves the project Moving -> Fixed convention used throughout the registration pipeline.

## Current decision rule

Ratio threshold 0.75 was carried through Stage 2 and is now frozen for the Stage 3 ORB versus SIFT comparison. The same minimum-match rule, RANSAC settings, control points, and geometric success thresholds are applied to both front-ends in Stage 3.

## Stage 2: Shared RANSAC geometry

Stage 2 connects the validated SIFT front-end to the existing similarity and affine RANSAC modules. No SIFT-specific robust estimator is introduced.

The controlled Stage 2 configuration contains seven similarity cases, four ordinary affine cases, and two affine failure probes. Target Windows validation completed on 2026-09-29 with `329 passed in 8.73s`. The experiment produced 12 / 13 matching successes, 12 / 13 RANSAC successes, and 12 / 13 results inside the configured geometric tolerances.

The repeated-pattern affine probe retained no ratio-filtered SIFT matches, so it failed before RANSAC. The low-texture affine probe retained 17 filtered matches, 15 RANSAC inliers, and produced 1.247 px TRE. These two cases remain separate because insufficient distinctive correspondences and weak texture are different failure mechanisms.

The validated Stage 2 snapshot is `reports/week04_sift_stage02_ransac.json`.

## Stage 3: Frozen ORB versus SIFT comparison

Stage 3 is implemented and has a development run. Both front-ends are evaluated on the same 12 cases with identical geometry, ratio threshold, minimum-match rule, RANSAC settings, control points, and geometric success criteria. Only the feature representation and descriptor metric differ.

Development evidence currently shows 10 / 12 ORB results and 11 / 12 SIFT results inside tolerance. SIFT recovered the low-texture affine probe in the development run, while ORB did not. Both front-ends failed the repeated-pattern probe before a valid geometric result was returned. SIFT was substantially slower in this environment.

These observations are not the final retention decision. The target Windows Stage 3 run must be recorded first. The complete comparison design and current evidence are documented in `docs/ORB_VS_SIFT_COMPARISON.md`.

## Final extension decision

The frozen Stage 3 comparison was validated on the target Windows environment with `333 passed in 3.57s`. SIFT was inside tolerance on 11 / 12 cases compared with 10 / 12 for ORB, recovered `low_texture_affine`, and produced lower median TRE on the comparison subset. Its mean total runtime was substantially higher.

Decision: **RETAIN AS OPTIONAL COMPLEMENT**. ORB remains the core feature baseline, and SIFT is retained for selected difficult cases and later robustness analysis.
