# Week 4 Progress: Feature-Based Registration with Robust Model Estimation

## Current status

Days 16 through 20 are complete and validated on the target Windows environment. Week 4 is complete.

## Day 16: ORB feature detection

Implemented:

- configurable ORB keypoint detection;
- 32-byte binary descriptor extraction;
- serializable keypoint metadata;
- deterministic grayscale-to-uint8 input conversion;
- optional detection masks;
- safe no-feature failure handling;
- 4 x 4 spatial-coverage diagnostic;
- keypoint visualization;
- controlled experiment across tracked camera, coins, and moon images;
- compact quantitative report with observations, interpretation, limitations, and next decision.

Target Windows validation:

- full pytest suite completed successfully with exit code 0;
- 8 / 8 configured ORB cases produced descriptors in both images;
- mean moving-image keypoint count: 652.0;
- mean moving-image spatial coverage: 0.695;
- mean moving-image detection runtime: 4.489 ms.

The strongest feature reduction occurred in the blurred moon case, where the moving image retained 36 keypoints compared with 585 in the fixed image and spatial coverage fell to 0.375. The rotated coins case retained 786 moving-image keypoints with coverage of 0.938. Several camera cases reached the 800-feature cap, so their keypoint counts are capped values rather than total detectable-feature counts.

## Day 17: ORB descriptor matching

Implemented:

- Hamming-distance descriptor matching;
- KNN matching with configurable ratio filtering;
- mutual nearest-neighbor cross-check matching;
- accepted-match Hamming-distance summaries;
- fixed and moving correspondence spatial coverage;
- tentative, filtered, and cross-check match visualizations;
- ratio-threshold sweep;
- safe failures for unavailable descriptors and insufficient filtered matches.

Target Windows validation:

- `270 passed in 3.93s`;
- 9 / 9 configured cases retained at least 8 KNN matches at ratio threshold 0.75;
- mean KNN accepted matches: 471.3;
- mean KNN minimum spatial coverage: 0.569;
- 9 / 9 cases retained at least 8 cross-checked matches;
- mean cross-check accepted matches: 509.0;
- mean cross-check minimum spatial coverage: 0.597.

The blurred moon case remained the weakest correspondence case with 29 KNN matches and minimum coverage of 0.375. Relaxing the ratio threshold increased retained matches, but Day 17 did not determine whether those additional correspondences were geometrically correct.

## Day 18: RANSAC similarity estimation

Implemented:

- Moving -> Fixed similarity estimation using OpenCV RANSAC;
- configurable reprojection threshold, confidence, maximum trials, refinement iterations, minimum inliers, and minimum inlier ratio;
- inlier and outlier masks;
- reprojection-residual statistics;
- TRE, rotation error, scale error, and centered translation error against exact ground truth;
- registered-image, edge-overlay, inlier-match, outlier-match, and residual visualizations;
- safe failure handling for insufficient matches and failed estimation;
- controlled correspondence-outlier injection.

Target Windows validation:

- `283 passed`;
- 8 / 8 RANSAC calls succeeded;
- 8 / 8 cases were inside the configured Day 18 development tolerances;
- mean inlier ratio: 0.884;
- median TRE: 0.277 px;
- maximum TRE: 0.556 px;
- the controlled outlier experiment injected 126 incorrect correspondences and RANSAC rejected all 126;
- the outlier-injection case achieved 0.360 px TRE.

The lowest target-run inlier ratio occurred in the blurred similarity case at 0.788. The largest TRE occurred in the large similarity case at 0.556 px.

The key reporting distinction is now explicit: descriptor-filter success, RANSAC model-estimation success, and ground-truth geometric success are three different states.

## Day 19: Affine RANSAC and robustness diagnostics

Implemented:

- general affine RANSAC estimation from ORB correspondences;
- similarity-versus-affine comparison on shared correspondences;
- correspondence grid-coverage and collinearity checks;
- transform plausibility checks for near-singular matrices, reflection, principal scale, condition number, shear, and translation magnitude;
- normalized gradient-energy and keypoint-density texture diagnostics;
- controlled low-texture and repeated-pattern cases;
- occlusion and restricted-field-of-view affine cases;
- ORB ratio-threshold and RANSAC reprojection-threshold sweep;
- explicit degeneracy probes with stored failure reasons.

Target Windows validation:

- `304 passed in 4.27s`;
- 7 / 9 affine RANSAC cases succeeded;
- 7 / 9 were within the configured Day 19 development tolerances;
- mean successful-case inlier ratio: 0.871;
- median affine TRE: 0.523 px;
- maximum returned TRE: 15.599 px;
- 3 / 3 degeneracy and plausibility probes produced their expected failure labels;
- 120 threshold-sweep combinations were recorded.

The true similarity reference produced nearly identical TRE for similarity and affine RANSAC, 0.657 px and 0.661 px. On every true-affine case where both models returned a numeric TRE, affine RANSAC produced the lower TRE. The low-texture case was rejected for insufficient RANSAC inliers, while the repeated-pattern case failed earlier because no matches survived descriptor filtering.

The threshold sweep produced 80 within-tolerance results across 120 combinations. The result supports keeping threshold choice separate from correspondence quality: changing thresholds did not recover cases that lacked sufficiently distinctive or reliable feature correspondences.

## Day 20: Integrated feature-based benchmark

Implemented:

- one integrated monomodal runner for Phase Correlation, ECC, ORB matching, similarity RANSAC, and affine RANSAC;
- separate shared comparison groups for translation, rigid, and affine geometry;
- separate low-texture and repeated-pattern feature diagnostics;
- model-aware tolerance checks and common result records;
- representative registration, match, and inlier figures;
- shared-case TRE plots and compact report snapshots;
- explicit comparison notes to prevent incompatible motion models from being collapsed into one ranking.

Target Windows validation:

- `314 passed in 4.36s`;
- 13 cases and 32 method executions;
- 30 / 32 method-level successes;
- 26 / 32 inside the configured Day 20 development tolerances;
- translation shared cases: Phase Correlation 4 / 4, ECC Translation 4 / 4, ORB + RANSAC Similarity 3 / 4;
- rigid shared cases: ECC Rigid 2 / 3, ORB + RANSAC Similarity 3 / 3;
- affine shared cases: ECC Affine Single 3 / 4, ECC Affine Multiresolution 3 / 4, ORB + RANSAC Affine 4 / 4.

The low-texture diagnostic failed before matching because too few descriptors were available. The repeated-pattern diagnostic retained 62 filtered matches but only 7 RANSAC inliers, and the affine estimate was rejected for insufficient RANSAC inliers.

## Week 4 conclusion

The core feature-based stage is complete. ORB detection, descriptor filtering, similarity and affine RANSAC, degeneracy checks, texture diagnostics, threshold sweeps, and the integrated shared-case benchmark are all validated. Before multimodal registration begins, the optional three-stage SIFT comparison is being completed.

## Optional SIFT extension before Week 5

The three-stage optional SIFT extension is complete and validated on the target Windows environment.

Stage 1 implemented SIFT detection, 128-dimensional floating-point descriptors, L2 KNN matching, ratio filtering, spatial-coverage diagnostics, and the threshold sweep. Target validation produced 7 / 7 matching successes and `327 passed in 9.44s`.

Stage 2 reused the existing similarity and affine RANSAC modules. Target validation produced 12 / 13 matching successes, 12 / 13 RANSAC successes, 12 / 13 results inside tolerance, and `329 passed in 8.73s`.

Stage 3 used a frozen 12-case paired ORB versus SIFT comparison. Target Windows validation produced `333 passed in 3.57s`. ORB was within tolerance on 10 / 12 cases and SIFT on 11 / 12. Ten cases passed with both methods, `low_texture_affine` passed only with SIFT, and `repeated_pattern_affine` failed for both. Median numeric TRE was 0.402 px for ORB and 0.116 px for SIFT. Mean total runtime was 18.982 ms for ORB and 55.566 ms for SIFT.

The final decision is **RETAIN AS OPTIONAL COMPLEMENT**. SIFT provides a measurable geometric benefit on this subset and recovers one difficult low-texture case, but it has a substantially higher runtime cost. ORB therefore remains the core feature baseline. SIFT is retained as an optional method for selected difficult cases and later robustness analysis.

Week 4 and its optional extension are now closed. The next stage is Week 5 Mutual Information registration.
