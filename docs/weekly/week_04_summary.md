# Week 4 Progress: Feature-Based Registration with Robust Model Estimation

## Current status

Days 16 and 17 are complete and validated on the target Windows environment. Days 18 to 20 have not started.

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

This evidence remains descriptive. Feature matching and geometric registration have not yet been introduced, so Day 16 does not support conclusions about correspondence correctness or registration accuracy.

## Day 17: ORB descriptor matching

Implemented:

- Hamming-distance descriptor matching with moving descriptors as queries and fixed descriptors as references;
- KNN matching with configurable ratio filtering;
- mutual nearest-neighbor cross-check matching;
- configurable minimum accepted-match requirement and optional distance threshold;
- accepted-match Hamming-distance summaries;
- fixed and moving correspondence spatial coverage;
- tentative, filtered, and cross-check match visualizations;
- match-distance histograms;
- KNN ratio-threshold sweep;
- safe failures for unavailable descriptors and insufficient filtered matches;
- tracked experiment findings, interpretation, limitations, and next decision.

Target Windows run:

- 9 / 9 configured cases retained at least 8 matches with KNN ratio 0.75;
- mean KNN accepted matches: 471.3;
- mean KNN minimum spatial coverage: 0.569;
- 9 / 9 configured cases retained at least 8 cross-checked matches;
- mean cross-check accepted matches: 509.0;
- mean cross-check minimum spatial coverage: 0.597.

Target Windows validation also completed with `270 passed in 3.93s`.

The blurred moon case remained the weakest correspondence case with 29 KNN matches, 32 cross-checked matches, and minimum coverage of 0.375. The rotated coins case had 0.812 minimum coverage under both strategies. Relaxing the KNN ratio threshold from 0.60 to 0.90 increased mean accepted matches from 404.2 to 556.7, but geometric validation is still required before choosing a threshold.

Day 17 does not estimate a transform. Accepted descriptor matches can still be geometric outliers, so these measurements are inputs for Day 18 rather than registration-accuracy results.

## Remaining plan

- Day 18: RANSAC similarity estimation and controlled outlier rejection
- Day 19: affine RANSAC, degeneracy checks, low-texture and robustness analysis
- Day 20: integrated feature-based benchmark and fair comparison with existing baselines
