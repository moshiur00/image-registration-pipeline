# ORB versus SIFT Controlled Comparison

## Status

Complete and validated on the target Windows environment on 2026-09-29.

Full repository validation: `333 passed in 3.57s`.

## Purpose

This optional extension tests whether SIFT provides a meaningful measurable benefit over the validated ORB feature baseline before Week 5. The comparison is paired and frozen. It is not a universal ranking of feature methods.

## Frozen comparison design

The following factors are identical for ORB and SIFT:

- fixed and moving image pair;
- known Moving -> Fixed ground-truth transform;
- transform model for each case;
- KNN ratio threshold 0.75;
- minimum-match rule;
- similarity or affine RANSAC settings;
- control points and geometric evaluation thresholds;
- result schema.

Only the feature front-end differs:

- ORB: binary descriptor with Hamming distance;
- SIFT: 128-dimensional floating-point descriptor with L2 distance.

## Target Windows result

The frozen experiment contains 12 cases and 24 registrations.

ORB:

- matching success: 11 / 12;
- RANSAC success: 10 / 12;
- within tolerance: 10 / 12;
- median numeric TRE: 0.402 px;
- mean inlier ratio: 0.865;
- mean total runtime: 18.982 ms.

SIFT:

- matching success: 11 / 12;
- RANSAC success: 11 / 12;
- within tolerance: 11 / 12;
- median numeric TRE: 0.116 px;
- mean inlier ratio: 0.945;
- mean total runtime: 55.566 ms.

Paired outcomes:

- both within tolerance: 10;
- ORB only: 0;
- SIFT only: 1;
- neither: 1.

`low_texture_affine` was the SIFT-only recovery. ORB returned 15.599 px TRE, while SIFT returned 1.247 px TRE and met the configured affine tolerance.

`repeated_pattern_affine` remained a shared failure. Neither front-end retained a usable filtered correspondence set for a valid final registration result in the frozen comparison.

## Runtime interpretation

The mean target Windows runtime was approximately 2.93 times higher for SIFT than ORB across the 12-case set. One ORB rotation run was unusually slow, so mean runtime alone should not be treated as a universal speed ratio. The overall evidence still shows a substantial SIFT extraction and matching cost in this experiment.

## Final SIFT decision

**RETAIN AS OPTIONAL COMPLEMENT**

The predefined decision priority was:

1. success rate;
2. TRE and geometric correctness;
3. difficult-case recovery;
4. RANSAC consistency;
5. runtime.

SIFT provides a measurable complementary benefit on this frozen subset. It recovered one difficult case that ORB did not recover, produced lower median TRE, and had a higher mean inlier ratio. It is not promoted to the core feature baseline because the improvement comes from a small controlled subset and SIFT has a substantially higher runtime cost. ORB remains the mandatory core feature method, while SIFT is retained for selected difficult cases and additional analysis.

## Limitations

- The comparison contains only 12 controlled cases.
- The result does not establish universal superiority of SIFT or ORB.
- Runtime is specific to the target Windows machine and current OpenCV build.
- Both methods still fail the repeated-pattern probe.
- The final benchmark in Weeks 7 and 8 should preserve failures rather than silently excluding them.

## Next step

The optional Week 4 SIFT extension is closed. Week 5 proceeds with Mutual Information registration for multimodal data.
